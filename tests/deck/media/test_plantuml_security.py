"""Tes branch keamanan renderer PlantUML: PNG, cache, proses, dan batas output."""

import base64
import ctypes
import io
import json
import os
import signal
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import autooffice.deck.media.plantuml as plantuml_module
from autooffice.deck.media.plantuml import (
    CACHE_FORMAT,
    PLANTUML_ENV_VAR,
    PNG_SIGNATURE,
    PlantUmlError,
    _base_command,
    _cache_metadata_matches,
    _cache_mtime,
    _close_windows_job,
    _copy_png,
    _create_windows_job,
    _discard_cache_entry,
    _executable_fingerprint,
    _feed_stdin,
    _FileCapture,
    _find_cached_png,
    _join_capture_threads,
    _OutputCapture,
    _plantuml_command,
    _png_problem,
    _read_cache_metadata,
    _read_source,
    _render_options,
    _run_captured,
    _source_sha256,
    _spawn_captured,
    _taskkill_tree,
    _terminate_process_tree,
    _theme_fingerprint,
    _validate_png,
    _validated_source,
    _wait_for_exit,
    _write_atomic_bytes,
    _write_cache_metadata,
    find_plantuml,
    plantuml_version,
    render_plantuml,
)
from autooffice.design.theme import resolve_theme

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
SOURCE_TEXT = "@startuml\nAlice -> Bob: halo\n@enduml\n"


@pytest.fixture(scope="module")
def theme():
    """Theme indigo untuk fingerprint cache."""
    return resolve_theme("indigo")


@pytest.fixture(autouse=True)
def _fresh_version_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolasi cache versi global antar test."""
    monkeypatch.setattr(plantuml_module, "_VERSION_CACHE", {})


def _chunk(kind: bytes, payload: bytes = b"") -> bytes:
    crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return len(payload).to_bytes(4, "big") + kind + payload + crc.to_bytes(4, "big")


def _ihdr(
    *,
    width: int = 1,
    height: int = 1,
    bit_depth: int = 8,
    color_type: int = 6,
    compression: int = 0,
    filter_method: int = 0,
    interlace: int = 0,
) -> bytes:
    return struct.pack(
        ">IIBBBBB",
        width,
        height,
        bit_depth,
        color_type,
        compression,
        filter_method,
        interlace,
    )


def _png(*chunks: bytes) -> bytes:
    return PNG_SIGNATURE + b"".join(chunks)


VALID_IHDR = _chunk(b"IHDR", _ihdr())
VALID_IDAT = _chunk(b"IDAT", b"")
VALID_IEND = _chunk(b"IEND", b"")
MINIMAL_PNG = _png(VALID_IHDR, VALID_IDAT, VALID_IEND)


def _completed(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
    truncated: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        truncated=truncated,
        stdout_truncated=False,
        stderr_truncated=False,
    )


FAKE_PLANTUML = """\
import base64
import sys

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

arguments = sys.argv[1:]
if arguments == ["--version"]:
    print("PlantUML version 1.2026.10 (test)")
    raise SystemExit(0)

source = sys.stdin.buffer.read()
if b"!include" in source and "-secure" in arguments:
    print("SecurityException: !include tidak diizinkan", file=sys.stderr)
    raise SystemExit(200)
sys.stdout.buffer.write(PNG)
sys.stdout.buffer.flush()
"""


def install_fake_plantuml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pasang executable PlantUML palsu minimal yang menghormati ``-secure``."""
    script = tmp_path / "fake_plantuml_security.py"
    script.write_text(FAKE_PLANTUML, encoding="utf-8", newline="\n")
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(script))
    return script


def write_source(tmp_path: Path, name: str = "flow.puml", text: str = SOURCE_TEXT) -> Path:
    source = tmp_path / name
    source.write_text(text, encoding="utf-8")
    return source


def make_directory_symlink(link: Path, target: Path) -> None:
    """Buat symlink direktori; Windows memakai junction bila symlink ditolak."""
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError as error:
        if os.name != "nt":
            pytest.skip(f"symlink direktori tidak didukung: {error}")
        command = os.environ.get("COMSPEC", "cmd.exe")
        completed = subprocess.run(
            [command, "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            pytest.skip(
                "symlink direktori dan junction tidak dapat dibuat: "
                f"symlink={error}; junction={detail or 'tanpa output'}"
            )


def remove_directory_symlink(link: Path) -> None:
    """Hapus symlink atau junction direktori tanpa menyentuh targetnya."""
    try:
        if link.is_symlink():
            link.unlink()
        elif link.is_junction():
            os.rmdir(link)
    except OSError:
        return


def terminate_process(pid: int) -> None:
    """Hentikan proses uji; aman dipanggil untuk PID yang sudah berhenti."""
    if os.name == "nt":
        process_terminate = 0x0001
        handle = ctypes.windll.kernel32.OpenProcess(process_terminate, False, pid)
        if not handle:
            return
        try:
            ctypes.windll.kernel32.TerminateProcess(handle, 1)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return


def read_process_id(path: Path) -> int | None:
    """Baca PID yang ditulis proses uji; None bila berkas belum ada atau rusak."""
    try:
        return int(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        pytest.param(b"", "terlalu pendek", id="empty"),
        pytest.param(b"\x89PNG", "terlalu pendek", id="too-short"),
        pytest.param(
            b"\x00" * 8 + MINIMAL_PNG[8:],
            "signature tidak valid",
            id="bad-signature",
        ),
        pytest.param(
            _png(_chunk(b"IDAT", b""), VALID_IEND),
            "IHDR tidak valid",
            id="missing-ihdr",
        ),
        pytest.param(
            _png(_chunk(b"IHDR", b"\x00" * 12), VALID_IDAT, VALID_IEND),
            "IHDR tidak valid",
            id="bad-ihdr-length",
        ),
        pytest.param(
            _png(_chunk(b"IHDR", _ihdr(width=0)), VALID_IDAT, VALID_IEND),
            "dimensi nol",
            id="zero-dimension",
        ),
        pytest.param(
            _png(_chunk(b"IHDR", _ihdr(height=0)), VALID_IDAT, VALID_IEND),
            "dimensi nol",
            id="zero-height",
        ),
        pytest.param(
            _png(VALID_IHDR, VALID_IHDR, VALID_IDAT, VALID_IEND),
            "IHDR ganda",
            id="double-ihdr",
        ),
        pytest.param(
            _png(VALID_IHDR, VALID_IEND),
            "IDAT tidak ditemukan",
            id="missing-idat",
        ),
        pytest.param(
            _png(VALID_IHDR, VALID_IDAT),
            "IEND tidak ditemukan",
            id="missing-iend",
        ),
        pytest.param(MINIMAL_PNG + b"x", "data setelah IEND", id="trailing-data"),
        pytest.param(
            MINIMAL_PNG[:-1] + bytes([MINIMAL_PNG[-1] ^ 0xFF]),
            "CRC chunk IEND rusak",
            id="bad-crc",
        ),
        pytest.param(_png(VALID_IHDR) + b"\x00\x00", "chunk terpotong", id="cut-header"),
        pytest.param(
            PNG_SIGNATURE + (0x80000000).to_bytes(4, "big") + b"IDAT" + b"\x00" * 4,
            "panjang chunk tidak valid",
            id="huge-length",
        ),
        pytest.param(
            PNG_SIGNATURE + (0).to_bytes(4, "big") + b"\x00\x00\x00\x00" + b"\x00" * 4,
            "tipe chunk tidak valid",
            id="bad-type",
        ),
        pytest.param(
            PNG_SIGNATURE + (13).to_bytes(4, "big") + b"IHDR" + b"\x00" * 5,
            "chunk terpotong",
            id="cut-ihdr-payload",
        ),
        pytest.param(
            _png(VALID_IHDR) + (10).to_bytes(4, "big") + b"IDAT" + b"abc",
            "chunk terpotong",
            id="cut-idat-payload",
        ),
        pytest.param(
            _png(VALID_IHDR) + (4).to_bytes(4, "big") + b"IDAT" + b"abcd" + b"\x00\x00",
            "CRC terpotong",
            id="cut-crc",
        ),
        pytest.param(
            _png(VALID_IHDR, VALID_IDAT, _chunk(b"IEND", b"x")),
            "IEND tidak valid",
            id="iend-with-payload",
        ),
        pytest.param(
            _png(_chunk(b"IHDR", _ihdr(color_type=1)), VALID_IDAT, VALID_IEND),
            "color type tidak valid",
            id="bad-color-type",
        ),
        pytest.param(
            _png(_chunk(b"IHDR", _ihdr(color_type=0, bit_depth=3)), VALID_IDAT, VALID_IEND),
            "bit depth tidak valid",
            id="bad-bit-depth",
        ),
        pytest.param(
            _png(_chunk(b"IHDR", _ihdr(compression=1)), VALID_IDAT, VALID_IEND),
            "parameter IHDR tidak valid",
            id="bad-ihdr-parameter",
        ),
        pytest.param(
            _png(_chunk(b"IHDR", _ihdr(interlace=2)), VALID_IDAT, VALID_IEND),
            "parameter IHDR tidak valid",
            id="bad-interlace",
        ),
    ],
)
def test_png_problem_rejects_malformed_chunks(
    tmp_path: Path,
    payload: bytes,
    reason: str,
) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(payload)

    assert _png_problem(path) == reason


def test_png_problem_accepts_multiple_idat_chunks(tmp_path: Path) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(_png(VALID_IHDR, VALID_IDAT, VALID_IDAT, VALID_IEND))

    assert _png_problem(path) is None


def test_png_problem_reports_stat_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(MINIMAL_PNG)
    real_stat = Path.stat

    def fail_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == path:
            raise OSError("stat gagal disengaja")
        return real_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", fail_stat)

    problem = _png_problem(path)

    assert problem is not None
    assert problem.startswith("tidak dapat dibaca")


def test_validate_png_reports_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(MINIMAL_PNG)
    real_open = Path.open

    def fail_open(self: Path, *args: object, **kwargs: object) -> Any:
        if self == path:
            raise OSError("buka gagal disengaja")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_open)

    with pytest.raises(PlantUmlError, match="tidak dapat dibaca") as error:
        _validate_png(path)

    assert str(path) in str(error.value)


def test_valid_png_passes_validation(tmp_path: Path) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(MINIMAL_PNG)

    assert _png_problem(path) is None
    _validate_png(path)


def test_validated_source_reports_stat_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = write_source(tmp_path)
    real_stat = Path.stat
    real_is_file = Path.is_file

    def fail_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == path:
            raise OSError("stat gagal disengaja")
        return real_stat(self, follow_symlinks=follow_symlinks)

    def existing_is_file(self: Path) -> bool:
        if self == path:
            return True
        return real_is_file(self)

    monkeypatch.setattr(Path, "stat", fail_stat)
    monkeypatch.setattr(Path, "is_file", existing_is_file)

    with pytest.raises(PlantUmlError, match="tidak dapat dibaca") as error:
        _validated_source(path)

    assert str(path) in str(error.value)


def test_validated_source_rejects_control_characters(tmp_path: Path) -> None:
    with pytest.raises(PlantUmlError, match="kontrol") as error:
        _validated_source(tmp_path / "flow\x01.puml")

    assert error.value.code == "PLANTUML-SOURCE"


def test_validated_source_rejects_empty_string_path() -> None:
    class EmptyPath:
        def __str__(self) -> str:
            return ""

    with pytest.raises(PlantUmlError, match="kosong"):
        _validated_source(EmptyPath())


def test_resolve_plantuml_source_reports_stat_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "flow.puml"
    path.write_text(SOURCE_TEXT, encoding="utf-8")
    resolved = path.resolve()
    real_stat = Path.stat
    real_is_file = Path.is_file

    def fail_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == resolved:
            raise OSError("stat gagal disengaja")
        return real_stat(self, follow_symlinks=follow_symlinks)

    def existing_is_file(self: Path) -> bool:
        if self == resolved:
            return True
        return real_is_file(self)

    monkeypatch.setattr(Path, "stat", fail_stat)
    monkeypatch.setattr(Path, "is_file", existing_is_file)

    with pytest.raises(PlantUmlError, match="tidak dapat dibaca"):
        plantuml_module.resolve_plantuml_source(tmp_path, "flow.puml")


def test_executable_fingerprint_returns_zero_when_stat_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "hilang.py"
    monkeypatch.setattr(Path, "stat", lambda *_args, **_kwargs: _raise_stat_error())

    assert _executable_fingerprint(path) == (str(path), 0, 0)


def _raise_stat_error() -> os.stat_result:
    raise OSError("stat gagal disengaja")


def test_read_source_reports_stat_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = write_source(tmp_path)
    monkeypatch.setattr(Path, "stat", lambda *_args, **_kwargs: _raise_stat_error())

    with pytest.raises(PlantUmlError, match="tidak dapat dibaca"):
        _read_source(path)


def test_read_source_reports_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = write_source(tmp_path)

    def fail_read_bytes(self: Path) -> bytes:
        raise OSError("baca gagal disengaja")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)

    with pytest.raises(PlantUmlError, match="tidak dapat dibaca"):
        _read_source(path)


def test_read_source_rejects_file_grown_after_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plantuml_module, "MAX_SOURCE_BYTES", 8)
    path = write_source(tmp_path)
    monkeypatch.setattr(Path, "stat", lambda *_args, **_kwargs: SimpleNamespace(st_size=1))
    monkeypatch.setattr(Path, "read_bytes", lambda _self: b"a" * 9)

    with pytest.raises(PlantUmlError, match="lebih dari"):
        _read_source(path)


def test_feed_stdin_handles_none_and_broken_streams() -> None:
    _feed_stdin(None, b"data")

    class BrokenStream:
        def __init__(self) -> None:
            self.closed = False

        def write(self, _data: bytes) -> None:
            raise OSError("tulis gagal")

        def flush(self) -> None:
            raise AssertionError("flush tidak boleh dipanggil")

        def close(self) -> None:
            self.closed = True

    stream = BrokenStream()
    _feed_stdin(stream, b"data")

    assert stream.closed is True


def test_source_sha256_streaming_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plantuml_module, "MAX_SOURCE_BYTES", 8)
    source = write_source(tmp_path, text="a" * 9)

    with pytest.raises(PlantUmlError, match="terlalu besar"):
        _source_sha256(source)


def test_base_command_handles_python_and_binary_executables() -> None:
    assert _base_command(Path("tool.py")) == [sys.executable, "tool.py"]
    assert _base_command(Path("tool.pyw")) == [sys.executable, "tool.pyw"]
    assert _base_command(Path("plantuml.exe")) == ["plantuml.exe"]


def test_jar_command_includes_headless_java(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    java = tmp_path / "java"
    monkeypatch.setattr(plantuml_module, "find_java", lambda: java)

    jar = tmp_path / "plantuml.jar"
    command = _plantuml_command(jar, "#FFFFFF")

    assert command[0:4] == [str(java), "-Djava.awt.headless=true", "-jar", str(jar)]
    assert "-secure" in command
    assert "-pipe" in command


def test_render_options_capture_security_relevant_values(theme) -> None:
    options = _render_options(theme.colors.background)

    assert options == {
        "format": "png",
        "dpi": 192,
        "layout": "smetana",
        "background": theme.colors.background,
        "secure": True,
    }


def test_plantuml_version_timeout_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "plantuml_timeout.py"
    script.write_text("# fake\n", encoding="utf-8")

    def run(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired("plantuml", 30)

    monkeypatch.setattr(plantuml_module, "_run_captured", run)

    with pytest.raises(PlantUmlError, match="melebihi batas waktu"):
        plantuml_version(script)


def test_plantuml_version_truncated_output_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "plantuml_truncated.py"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setattr(
        plantuml_module,
        "_run_captured",
        lambda *_args, **_kwargs: _completed(
            stdout="PlantUML version 1.2026.10 (test)",
            truncated=True,
        ),
    )

    with pytest.raises(PlantUmlError, match="batas output"):
        plantuml_version(script)


def test_cache_metadata_roundtrip(tmp_path: Path) -> None:
    cache_path = tmp_path / "plantuml-abc.png"
    payload = {
        "format": CACHE_FORMAT,
        "digest": "abc",
        "source_sha256": "a" * 64,
        "theme": {"name": "indigo"},
        "plantuml_version": "1.2026.10",
        "options": {"format": "png"},
    }

    _write_cache_metadata(cache_path, payload)

    sidecar = cache_path.with_suffix(".json")
    assert json.loads(sidecar.read_text(encoding="utf-8")) == payload
    assert _read_cache_metadata(sidecar) == payload


def test_read_cache_metadata_rejects_oversized_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plantuml_module, "MAX_CACHE_METADATA_BYTES", 3)
    path = tmp_path / "plantuml-abc.json"
    path.write_text("1234", encoding="utf-8")

    assert _read_cache_metadata(path) is None


def test_read_cache_metadata_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "plantuml-abc.json"
    path.write_text("{", encoding="utf-8")

    assert _read_cache_metadata(path) is None


def test_read_cache_metadata_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "plantuml-abc.json"
    path.write_text("[]", encoding="utf-8")

    assert _read_cache_metadata(path) is None


def test_cache_metadata_matches_rejects_mismatches(theme) -> None:
    fingerprint = _theme_fingerprint(theme)
    background = theme.colors.background
    options = _render_options(background)
    payload: dict[str, object] = {
        "format": CACHE_FORMAT,
        "source_sha256": "a" * 64,
        "theme": fingerprint,
        "options": options,
    }
    expected = {
        "source_hash": "a" * 64,
        "theme_fingerprint": fingerprint,
        "background": background,
    }

    assert _cache_metadata_matches(payload, **expected)

    mismatches = [
        {**payload, "format": CACHE_FORMAT + 1},
        {**payload, "source_sha256": "b" * 64},
        {**payload, "theme": None},
        {**payload, "theme": {"name": "lain"}},
        {**payload, "options": None},
        {**payload, "options": {**options, "format": "svg"}},
        {**payload, "options": {**options, "dpi": 96}},
        {**payload, "options": {**options, "layout": "graphviz"}},
        {**payload, "options": {**options, "background": "#000000"}},
        {**payload, "options": {**options, "secure": False}},
    ]
    for mismatch in mismatches:
        assert _cache_metadata_matches(mismatch, **expected) is False


def test_find_cached_png_returns_none_on_glob_error(
    tmp_path: Path,
    theme,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_glob(*_args: object, **_kwargs: object) -> None:
        raise OSError("glob gagal disengaja")

    monkeypatch.setattr(Path, "glob", fail_glob)

    assert (
        _find_cached_png(
            tmp_path,
            source_hash="a" * 64,
            theme_fingerprint=_theme_fingerprint(theme),
            background=theme.colors.background,
        )
        is None
    )


def test_find_cached_png_removes_unreadable_metadata(
    tmp_path: Path,
    theme,
) -> None:
    metadata = tmp_path / "plantuml-rusak.json"
    metadata.write_text("{", encoding="utf-8")

    result = _find_cached_png(
        tmp_path,
        source_hash="a" * 64,
        theme_fingerprint=_theme_fingerprint(theme),
        background=theme.colors.background,
    )

    assert result is None
    assert not metadata.exists()


def test_find_cached_png_skips_matching_metadata_with_invalid_png(
    tmp_path: Path,
    theme,
) -> None:
    fingerprint = _theme_fingerprint(theme)
    background = theme.colors.background
    source_hash = "a" * 64
    cache_path = tmp_path / "plantuml-abc.png"
    cache_path.write_bytes(b"bukan png")
    _write_cache_metadata(
        cache_path,
        {
            "format": CACHE_FORMAT,
            "digest": "abc",
            "source_sha256": source_hash,
            "theme": fingerprint,
            "plantuml_version": "1.2026.10",
            "options": _render_options(background),
        },
    )

    result = _find_cached_png(
        tmp_path,
        source_hash=source_hash,
        theme_fingerprint=fingerprint,
        background=background,
    )

    assert result is None
    assert not cache_path.exists()
    assert not cache_path.with_suffix(".json").exists()


def test_find_cached_png_returns_valid_match(tmp_path: Path, theme) -> None:
    fingerprint = _theme_fingerprint(theme)
    background = theme.colors.background
    source_hash = "a" * 64
    cache_path = tmp_path / "plantuml-abc.png"
    cache_path.write_bytes(MINIMAL_PNG)
    _write_cache_metadata(
        cache_path,
        {
            "format": CACHE_FORMAT,
            "digest": "abc",
            "source_sha256": source_hash,
            "theme": fingerprint,
            "plantuml_version": "1.2026.10",
            "options": _render_options(background),
        },
    )

    assert (
        _find_cached_png(
            tmp_path,
            source_hash=source_hash,
            theme_fingerprint=fingerprint,
            background=background,
        )
        == cache_path
    )
    assert (
        _find_cached_png(
            tmp_path,
            source_hash="b" * 64,
            theme_fingerprint=fingerprint,
            background=background,
        )
        is None
    )


def test_cache_mtime_returns_zero_on_stat_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_stat(*_args: object, **_kwargs: object) -> None:
        raise OSError("stat gagal disengaja")

    monkeypatch.setattr(Path, "stat", fail_stat)

    assert _cache_mtime(tmp_path / "hilang.json") == 0


def test_discard_cache_entry_ignores_unlink_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = tmp_path / "plantuml-abc.png"
    cache_path.write_bytes(MINIMAL_PNG)
    metadata_path = cache_path.with_suffix(".json")
    metadata_path.write_text("{}", encoding="utf-8")
    attempted: list[Path] = []

    def fail_unlink(self: Path, *_args: object, **_kwargs: object) -> None:
        attempted.append(self)
        raise OSError("hapus gagal disengaja")

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    _discard_cache_entry(cache_path)

    assert attempted == [cache_path, metadata_path]
    assert cache_path.exists()
    assert metadata_path.exists()


def test_output_capture_handles_missing_and_broken_streams() -> None:
    capture = _OutputCapture(4)
    capture.drain(None)
    assert capture.data == b""
    assert capture.truncated is False

    class BrokenStream:
        def __init__(self, error: Exception) -> None:
            self.error = error

        def read(self, _size: int) -> bytes:
            raise self.error

    capture.drain(BrokenStream(OSError("baca gagal")))
    capture.drain(BrokenStream(ValueError("stream tertutup")))

    assert capture.data == b""
    assert capture.truncated is False


def test_output_capture_truncates_at_limit() -> None:
    capture = _OutputCapture(4)

    capture.drain(io.BytesIO(b"abcdef"))

    assert capture.data == b"abcd"
    assert capture.truncated is True


def test_file_capture_writes_binary_and_truncates_at_limit(tmp_path: Path) -> None:
    path = tmp_path / "render.bin"
    capture = _FileCapture(path, 4)

    class ChunkedStream:
        def __init__(self) -> None:
            self.chunks = [b"abcd", b"efgh"]

        def read(self, _size: int) -> bytes:
            return self.chunks.pop(0) if self.chunks else b""

    capture.drain(ChunkedStream())
    capture.close()

    assert path.read_bytes() == b"abcd"
    assert capture.written == 4
    assert capture.truncated is True


def test_file_capture_handles_missing_and_broken_streams(tmp_path: Path) -> None:
    path = tmp_path / "render.bin"
    capture = _FileCapture(path, 4)
    capture.drain(None)

    class BrokenStream:
        def read(self, _size: int) -> bytes:
            raise OSError("baca gagal")

    capture.drain(BrokenStream())
    capture.close()

    assert path.read_bytes() == b""
    assert capture.truncated is False


class _FakeThread:
    def __init__(self) -> None:
        self.joins = 0

    def join(self, timeout: float | None = None) -> None:
        self.joins += 1

    def is_alive(self) -> bool:
        return True


class _FakeStream:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.closed = False

    def close(self) -> None:
        self.closed = True
        if self.error is not None:
            raise self.error


def test_join_capture_threads_closes_streams_on_stuck_threads() -> None:
    threads = [_FakeThread(), _FakeThread()]
    stream = _FakeStream(error=OSError("tutup gagal"))
    process = SimpleNamespace(stdout=None, stderr=stream)

    _join_capture_threads(threads, process)

    assert [thread.joins for thread in threads] == [2, 2]
    assert stream.closed is True


class _WaitProcess:
    def __init__(
        self,
        outcomes: list[Exception | int],
        *,
        kill_error: Exception | None = None,
    ) -> None:
        self.outcomes = list(outcomes)
        self.kill_error = kill_error
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def kill(self) -> None:
        self.killed = True
        if self.kill_error is not None:
            raise self.kill_error


def test_wait_for_exit_kills_after_timeout() -> None:
    process = _WaitProcess([subprocess.TimeoutExpired("plantuml", 5), 0])

    _wait_for_exit(process)

    assert process.killed is True


def test_wait_for_exit_gives_up_after_second_timeout() -> None:
    process = _WaitProcess(
        [
            subprocess.TimeoutExpired("plantuml", 5),
            subprocess.TimeoutExpired("plantuml", 5),
        ]
    )

    _wait_for_exit(process)

    assert process.killed is True


def test_wait_for_exit_returns_when_kill_fails() -> None:
    process = _WaitProcess(
        [subprocess.TimeoutExpired("plantuml", 5)],
        kill_error=OSError("kill gagal"),
    )

    _wait_for_exit(process)

    assert process.killed is True


class _KillableProcess:
    pid = 4321

    def __init__(self) -> None:
        self.killed = False

    def kill(self) -> None:
        self.killed = True


def test_terminate_process_tree_uses_windows_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plantuml_module.os, "name", "nt")
    monkeypatch.setattr(plantuml_module, "_terminate_windows_job", lambda _job: True)
    taskkills: list[int] = []
    monkeypatch.setattr(plantuml_module, "_taskkill_tree", taskkills.append)
    process = _KillableProcess()

    _terminate_process_tree(process, 7)

    assert taskkills == []
    assert process.killed is False


@pytest.mark.parametrize("job", [7, None])
def test_terminate_process_tree_falls_back_to_taskkill(
    monkeypatch: pytest.MonkeyPatch,
    job: int | None,
) -> None:
    monkeypatch.setattr(plantuml_module.os, "name", "nt")
    monkeypatch.setattr(plantuml_module, "_terminate_windows_job", lambda _job: False)
    taskkills: list[int] = []
    monkeypatch.setattr(plantuml_module, "_taskkill_tree", taskkills.append)
    process = _KillableProcess()

    _terminate_process_tree(process, job)

    assert taskkills == [4321]
    assert process.killed is True


def test_terminate_process_tree_posix_uses_killpg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plantuml_module.os, "name", "posix")
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        plantuml_module.os,
        "killpg",
        lambda pid, sig: calls.append((pid, sig)),
        raising=False,
    )
    process = _KillableProcess()

    _terminate_process_tree(process, None)

    expected_signal = getattr(plantuml_module.signal, "SIGKILL", plantuml_module.signal.SIGTERM)
    assert calls == [(4321, expected_signal)]
    assert process.killed is False


def test_terminate_process_tree_posix_process_already_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plantuml_module.os, "name", "posix")
    monkeypatch.delattr(plantuml_module.os, "killpg", raising=False)
    process = _KillableProcess()

    _terminate_process_tree(process, None)

    assert process.killed is True


def test_terminate_process_tree_posix_killpg_raises_process_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plantuml_module.os, "name", "posix")

    def gone(_pid: int, _sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(plantuml_module.os, "killpg", gone, raising=False)
    process = _KillableProcess()

    _terminate_process_tree(process, None)

    assert process.killed is False


def test_terminate_process_tree_posix_falls_back_to_process_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plantuml_module.os, "name", "posix")

    def fail(_pid: int, _sig: int) -> None:
        raise OSError("killpg gagal")

    monkeypatch.setattr(plantuml_module.os, "killpg", fail, raising=False)
    process = _KillableProcess()

    _terminate_process_tree(process, None)

    assert process.killed is True


def test_terminate_process_tree_ignores_process_kill_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plantuml_module.os, "name", "posix")
    monkeypatch.delattr(plantuml_module.os, "killpg", raising=False)

    class KillFailProcess:
        pid = 4321

        def __init__(self) -> None:
            self.kill_calls = 0

        def kill(self) -> None:
            self.kill_calls += 1
            raise OSError("kill gagal")

    process = KillFailProcess()

    _terminate_process_tree(process, None)

    assert process.kill_calls == 1


def test_run_captured_closes_job_when_spawn_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int | None] = []
    monkeypatch.setattr(plantuml_module, "_create_windows_job", lambda: 7)

    def fail_spawn(_command: list[str]) -> None:
        raise OSError("spawn gagal disengaja")

    monkeypatch.setattr(plantuml_module, "_spawn_captured", fail_spawn)
    monkeypatch.setattr(plantuml_module, "_close_windows_job", closed.append)

    with pytest.raises(OSError, match="spawn gagal"):
        _run_captured(["plantuml"], timeout=1)

    assert closed == [7]


class _FakeProcess:
    pid = 1234

    def __init__(self) -> None:
        self.stdout = None
        self.stderr = None
        self.waits = 0

    def wait(self, timeout: float | None = None) -> int:
        self.waits += 1
        return 0


def test_run_captured_closes_job_when_assignment_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int | None] = []
    process = _FakeProcess()
    monkeypatch.setattr(plantuml_module, "_create_windows_job", lambda: 11)
    monkeypatch.setattr(plantuml_module, "_spawn_captured", lambda _command: process)
    monkeypatch.setattr(plantuml_module, "_assign_process_to_job", lambda _job, _pid: False)
    monkeypatch.setattr(plantuml_module, "_close_windows_job", closed.append)

    result = _run_captured(["plantuml"], timeout=1)

    assert result.returncode == 0
    assert closed == [11, None]


def test_run_captured_closes_job_handle_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(create=7, open=11, assign=1)
    process = _FakeProcess()
    monkeypatch.setattr(plantuml_module.os, "name", "nt")
    monkeypatch.setattr(plantuml_module, "_kernel32", lambda: kernel)
    monkeypatch.setattr(plantuml_module, "_spawn_captured", lambda _command: process)

    result = _run_captured(["plantuml"], timeout=1)

    assert result.returncode == 0
    assert kernel.AssignProcessToJobObject.calls == [((7, 11), {})]
    assert kernel.CloseHandle.calls == [((11,), {}), ((7,), {})]


def test_spawn_captured_uses_posix_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, Any] = {}

    class FakePopen:
        def __init__(self, command: list[str], **kwargs: Any) -> None:
            recorded["command"] = command
            recorded["kwargs"] = kwargs

    monkeypatch.setattr(plantuml_module.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(plantuml_module.os, "name", "posix")

    process = _spawn_captured(["plantuml"])

    assert isinstance(process, FakePopen)
    assert recorded["command"] == ["plantuml"]
    assert recorded["kwargs"]["start_new_session"] is True
    assert "creationflags" not in recorded["kwargs"]


class _FakeFunction:
    def __init__(self, result: int) -> None:
        self.result = result
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.argtypes: list[Any] = []
        self.restype: Any = None

    def __call__(self, *args: Any, **kwargs: Any) -> int:
        self.calls.append((args, kwargs))
        return self.result


def _fake_kernel(**results: int) -> SimpleNamespace:
    return SimpleNamespace(
        CreateJobObjectW=_FakeFunction(results.get("create", 1)),
        SetInformationJobObject=_FakeFunction(results.get("configure", 1)),
        CloseHandle=_FakeFunction(results.get("close", 1)),
        OpenProcess=_FakeFunction(results.get("open", 1)),
        AssignProcessToJobObject=_FakeFunction(results.get("assign", 1)),
        TerminateJobObject=_FakeFunction(results.get("terminate", 1)),
    )


def test_create_windows_job_returns_none_off_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plantuml_module.os, "name", "posix")

    assert _create_windows_job() is None


def test_create_windows_job_returns_none_when_creation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(create=0)
    monkeypatch.setattr(plantuml_module.os, "name", "nt")
    monkeypatch.setattr(plantuml_module, "_kernel32", lambda: kernel)

    assert _create_windows_job() is None
    assert kernel.CloseHandle.calls == []


def test_create_windows_job_closes_handle_when_configuration_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(configure=0)
    monkeypatch.setattr(plantuml_module.os, "name", "nt")
    monkeypatch.setattr(plantuml_module, "_kernel32", lambda: kernel)

    assert _create_windows_job() is None
    assert kernel.CloseHandle.calls == [((1,), {})]


def test_create_windows_job_returns_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(configure=1)
    monkeypatch.setattr(plantuml_module.os, "name", "nt")
    monkeypatch.setattr(plantuml_module, "_kernel32", lambda: kernel)

    assert _create_windows_job() == 1


def test_create_windows_job_sets_kill_on_job_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(create=7, configure=1)
    monkeypatch.setattr(plantuml_module.os, "name", "nt")
    monkeypatch.setattr(plantuml_module, "_kernel32", lambda: kernel)

    assert _create_windows_job() == 7

    assert kernel.CreateJobObjectW.calls == [((None, None), {})]
    assert len(kernel.SetInformationJobObject.calls) == 1
    arguments, keywords = kernel.SetInformationJobObject.calls[0]
    assert keywords == {}
    assert arguments[0] == 7
    assert arguments[1] == plantuml_module._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION
    information = arguments[2]._obj
    assert isinstance(information, plantuml_module._JobExtendedLimitInformation)
    assert (
        information.basic_limit_information.limit_flags
        == plantuml_module._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    )
    assert information.basic_limit_information.limit_flags == 0x00002000
    assert arguments[3] == ctypes.sizeof(plantuml_module._JobExtendedLimitInformation)


def test_close_windows_job_ignores_none_and_closes_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel()
    monkeypatch.setattr(plantuml_module, "_kernel32", lambda: kernel)

    _close_windows_job(None)
    assert kernel.CloseHandle.calls == []

    _close_windows_job(7)
    assert kernel.CloseHandle.calls == [((7,), {})]


def test_assign_process_to_job_reports_missing_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(open=0)
    monkeypatch.setattr(plantuml_module, "_kernel32", lambda: kernel)

    assert plantuml_module._assign_process_to_job(1, 2) is False


def test_assign_process_to_job_closes_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(open=2, assign=1)
    monkeypatch.setattr(plantuml_module, "_kernel32", lambda: kernel)

    assert plantuml_module._assign_process_to_job(1, 2) is True
    expected_access = plantuml_module._PROCESS_SET_QUOTA | plantuml_module._PROCESS_TERMINATE
    assert kernel.OpenProcess.calls == [((expected_access, 0, 2), {})]
    assert kernel.AssignProcessToJobObject.calls == [((1, 2), {})]
    assert kernel.CloseHandle.calls == [((2,), {})]


def test_terminate_windows_job_returns_success_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(terminate=1)
    monkeypatch.setattr(plantuml_module, "_kernel32", lambda: kernel)
    assert plantuml_module._terminate_windows_job(1) is True

    kernel = _fake_kernel(terminate=0)
    monkeypatch.setattr(plantuml_module, "_kernel32", lambda: kernel)
    assert plantuml_module._terminate_windows_job(1) is False


def test_taskkill_tree_requires_systemroot(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.delenv("SYSTEMROOT", raising=False)
    monkeypatch.setattr(plantuml_module.subprocess, "run", calls.append)

    _taskkill_tree(1234)

    assert calls == []


def test_taskkill_tree_ignores_missing_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setenv("SYSTEMROOT", str(tmp_path / "Windows"))
    monkeypatch.setattr(plantuml_module.subprocess, "run", calls.append)

    _taskkill_tree(1234)

    assert calls == []


def test_taskkill_tree_uses_absolute_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_root = tmp_path / "Windows"
    executable = system_root / "System32" / "taskkill.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setenv("SYSTEMROOT", str(system_root))
    monkeypatch.setattr(plantuml_module.subprocess, "run", fake_run)

    _taskkill_tree(4321)

    assert calls == [
        (
            [str(executable), "/PID", "4321", "/T", "/F"],
            {
                "stdin": subprocess.DEVNULL,
                "capture_output": True,
                "timeout": plantuml_module.TERMINATE_WAIT_TIMEOUT,
                "check": False,
            },
        )
    ]


@pytest.mark.parametrize("error", [OSError("run gagal"), subprocess.SubprocessError("gagal")])
def test_taskkill_tree_ignores_run_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    system_root = tmp_path / "Windows"
    executable = system_root / "System32" / "taskkill.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fail_run(command: list[str], **kwargs: Any) -> None:
        calls.append((command, kwargs))
        raise error

    monkeypatch.setenv("SYSTEMROOT", str(system_root))
    monkeypatch.setattr(plantuml_module.subprocess, "run", fail_run)

    _taskkill_tree(4321)

    assert calls == [
        (
            [str(executable), "/PID", "4321", "/T", "/F"],
            {
                "stdin": subprocess.DEVNULL,
                "capture_output": True,
                "timeout": plantuml_module.TERMINATE_WAIT_TIMEOUT,
                "check": False,
            },
        )
    ]


def test_copy_png_fsync_failure_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(MINIMAL_PNG)
    target = tmp_path / "out" / "target.png"

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("fsync gagal")

    monkeypatch.setattr(plantuml_module.os, "fsync", fail_fsync)

    with pytest.raises(PlantUmlError, match="Gagal menulis PNG"):
        _copy_png(source, target)

    assert not target.exists()
    assert list(target.parent.glob(".*.tmp")) == []


def test_copy_png_fdopen_failure_closes_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(MINIMAL_PNG)
    target = tmp_path / "out" / "target.png"

    def fail_fdopen(*_args: object, **_kwargs: object) -> None:
        raise OSError("fdopen gagal")

    monkeypatch.setattr(plantuml_module.os, "fdopen", fail_fdopen)

    with pytest.raises(PlantUmlError, match="Gagal menulis PNG"):
        _copy_png(source, target)

    assert not target.exists()
    assert list(target.parent.glob(".*.tmp")) == []


def test_write_atomic_bytes_fsync_failure_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "metadata.json"

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("fsync gagal")

    monkeypatch.setattr(plantuml_module.os, "fsync", fail_fsync)

    with pytest.raises(PlantUmlError, match="metadata cache"):
        _write_atomic_bytes(target, b"{}")

    assert not target.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_write_atomic_bytes_fdopen_failure_closes_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "metadata.json"

    def fail_fdopen(*_args: object, **_kwargs: object) -> None:
        raise OSError("fdopen gagal")

    monkeypatch.setattr(plantuml_module.os, "fdopen", fail_fdopen)

    with pytest.raises(PlantUmlError, match="metadata cache"):
        _write_atomic_bytes(target, b"{}")

    assert not target.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_render_plantuml_writes_cache_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    install_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"

    render_plantuml(source, tmp_path / "flow.png", theme=theme, cache_dir=cache)

    sidecars = list(cache.glob("plantuml-*.json"))
    assert len(sidecars) == 1
    payload = _read_cache_metadata(sidecars[0])
    assert payload is not None
    assert payload["format"] == CACHE_FORMAT
    assert payload["digest"] == sidecars[0].stem.removeprefix("plantuml-")
    assert payload["plantuml_version"] == "1.2026.10"
    assert payload["options"] == _render_options(theme.colors.background)


def test_secure_flag_blocks_include_directive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    install_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(
        tmp_path,
        text="@startuml\n!include https://example.com/rahasia.puml\n@enduml\n",
    )
    out = tmp_path / "flow.png"
    cache = tmp_path / "cache"

    with pytest.raises(PlantUmlError, match="SecurityException") as error:
        render_plantuml(source, out, theme=theme, cache_dir=cache)

    assert error.value.code == "PLANTUML-RENDER"
    assert not out.exists()
    assert list(cache.glob("plantuml-*.png")) == []
    assert list(cache.glob("plantuml-*.json")) == []


@pytest.mark.integration
def test_real_plantuml_rejects_include_with_secure_mode(tmp_path: Path, theme) -> None:
    """Engine asli harus menolak ``!include`` dan tidak meninggalkan PNG."""
    executable = find_plantuml()
    if executable is None:
        pytest.skip("PlantUML tidak tersedia; set AUTOOFFICE_PLANTUML atau pasang plantuml di PATH")
    included = tmp_path / "other.puml"
    included.write_text("@startuml\nAlice -> Bob: included\n@enduml\n", encoding="utf-8")
    source = write_source(tmp_path, text="@startuml\n!include other.puml\n@enduml\n")
    out = tmp_path / "flow.png"
    cache = tmp_path / "cache"

    with pytest.raises(PlantUmlError) as error:
        render_plantuml(source, out, theme=theme, cache_dir=cache)

    assert error.value.code == "PLANTUML-RENDER"
    assert "cannot include" in str(error.value)
    assert not out.exists()
    assert list(cache.glob("plantuml-*.png")) == []
    assert list(cache.glob("plantuml-*.json")) == []


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("source_sha256", "b" * 64),
        ("theme", {"name": "palsu"}),
        ("options", None),
        ("format", CACHE_FORMAT + 1),
    ],
)
def test_tampered_cache_metadata_is_ignored_without_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
    key: str,
    value: object,
) -> None:
    script = install_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"
    render_plantuml(source, tmp_path / "first.png", theme=theme, cache_dir=cache)
    sidecar = next(cache.glob("plantuml-*.json"))
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload[key] = value
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    script.unlink()
    monkeypatch.delenv(PLANTUML_ENV_VAR, raising=False)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    out = tmp_path / "second.png"

    with pytest.raises(PlantUmlError, match="tidak ditemukan"):
        render_plantuml(source, out, theme=theme, cache_dir=cache)

    assert not out.exists()


def test_cache_metadata_tampering_does_not_copy_other_png(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    script = install_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    other = write_source(tmp_path, "other.puml", "@startuml\nA -> C\n@enduml\n")
    cache = tmp_path / "cache"
    render_plantuml(other, tmp_path / "other.png", theme=theme, cache_dir=cache)
    render_plantuml(source, tmp_path / "first.png", theme=theme, cache_dir=cache)
    digest = plantuml_module.cache_digest(
        source,
        theme=theme,
        plantuml_version="1.2026.10",
    )
    source_sidecar = cache / f"plantuml-{digest}.json"
    payload = json.loads(source_sidecar.read_text(encoding="utf-8"))
    payload["source_sha256"] = "c" * 64
    source_sidecar.write_text(json.dumps(payload), encoding="utf-8")
    script.unlink()
    monkeypatch.delenv(PLANTUML_ENV_VAR, raising=False)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    with pytest.raises(PlantUmlError, match="tidak ditemukan"):
        render_plantuml(source, tmp_path / "second.png", theme=theme, cache_dir=cache)

    assert not (tmp_path / "second.png").exists()


def test_copy_png_ignores_predictable_stale_temp_symlink(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(PNG_1X1)
    target = tmp_path / "out" / "target.png"
    target.parent.mkdir()
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("jangan diubah", encoding="utf-8")
    stale = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        stale.symlink_to(sentinel)
    except OSError as error:
        pytest.skip(f"symlink tidak didukung: {error}")

    _copy_png(source, target)

    assert sentinel.read_text(encoding="utf-8") == "jangan diubah"
    assert target.read_bytes() == PNG_1X1
    assert stale.is_symlink()


def test_render_rejects_cache_symlink_to_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    install_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    target = tmp_path / "cache-target"
    target.write_text("bukan folder", encoding="utf-8")
    cache = tmp_path / "cache"
    try:
        cache.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlink tidak didukung: {error}")

    with pytest.raises(PlantUmlError, match="bukan direktori") as error:
        render_plantuml(source, tmp_path / "flow.png", theme=theme, cache_dir=cache)

    assert error.value.code == "PLANTUML-CACHE"


def test_render_rejects_dangling_cache_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    install_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"
    try:
        cache.symlink_to(tmp_path / "hilang", target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink tidak didukung: {error}")

    with pytest.raises(PlantUmlError, match="Gagal menyiapkan cache") as error:
        render_plantuml(source, tmp_path / "flow.png", theme=theme, cache_dir=cache)

    assert error.value.code == "PLANTUML-CACHE"


def test_render_rejects_output_symlink_to_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    install_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    directory = tmp_path / "outside-dir"
    directory.mkdir()
    out = tmp_path / "flow.png"
    make_directory_symlink(out, directory)
    try:
        with pytest.raises(PlantUmlError, match="berupa file") as error:
            render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")
    finally:
        remove_directory_symlink(out)

    assert error.value.code == "PLANTUML-OUTPUT"


def test_render_does_not_follow_output_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    install_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    sentinel = tmp_path / "sentinel.png"
    sentinel.write_bytes(b"jangan ditimpa")
    out = tmp_path / "flow.png"
    try:
        out.symlink_to(sentinel)
    except OSError as error:
        pytest.skip(f"symlink tidak didukung: {error}")

    render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert sentinel.read_bytes() == b"jangan ditimpa"
    assert not out.is_symlink()
    assert out.read_bytes() == PNG_1X1


def test_cache_entry_symlink_is_replaced_without_touching_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    install_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    sentinel = tmp_path / "sentinel.bin"
    sentinel.write_bytes(b"bukan png")
    digest = plantuml_module.cache_digest(
        source,
        theme=theme,
        plantuml_version="1.2026.10",
    )
    cache_path = cache / f"plantuml-{digest}.png"
    try:
        cache_path.symlink_to(sentinel)
    except OSError as error:
        pytest.skip(f"symlink tidak didukung: {error}")

    out = tmp_path / "flow.png"
    render_plantuml(source, out, theme=theme, cache_dir=cache)

    assert sentinel.read_bytes() == b"bukan png"
    assert not cache_path.is_symlink()
    assert cache_path.read_bytes() == PNG_1X1
    assert out.read_bytes() == PNG_1X1


def test_cache_metadata_symlink_is_removed_without_touching_target(
    tmp_path: Path,
    theme,
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    sentinel = tmp_path / "sentinel.json"
    sentinel.write_text("{", encoding="utf-8")
    metadata = cache / "plantuml-abc.json"
    try:
        metadata.symlink_to(sentinel)
    except OSError as error:
        pytest.skip(f"symlink file tidak didukung: {error}")

    result = _find_cached_png(
        cache,
        source_hash="a" * 64,
        theme_fingerprint=_theme_fingerprint(theme),
        background=theme.colors.background,
    )

    assert result is None
    assert not metadata.exists()
    assert sentinel.read_text(encoding="utf-8") == "{"


def test_render_does_not_copy_symlinked_valid_cache_png(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    install_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    target = tmp_path / "valid-target.png"
    target.write_bytes(MINIMAL_PNG)
    digest = plantuml_module.cache_digest(source, theme=theme, plantuml_version="1.2026.10")
    cache_path = cache / f"plantuml-{digest}.png"
    try:
        cache_path.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlink file tidak didukung: {error}")
    _write_cache_metadata(
        cache_path,
        {
            "format": CACHE_FORMAT,
            "digest": digest,
            "source_sha256": plantuml_module._source_sha256(source),
            "theme": _theme_fingerprint(theme),
            "plantuml_version": "1.2026.10",
            "options": _render_options(theme.colors.background),
        },
    )
    out = tmp_path / "flow.png"

    render_plantuml(source, out, theme=theme, cache_dir=cache)

    assert out.read_bytes() == PNG_1X1
    assert target.read_bytes() == MINIMAL_PNG
    assert not cache_path.is_symlink()
    assert cache_path.read_bytes() == PNG_1X1


def test_find_cached_png_rejects_symlinked_valid_png(tmp_path: Path, theme) -> None:
    fingerprint = _theme_fingerprint(theme)
    background = theme.colors.background
    source_hash = "a" * 64
    target = tmp_path / "valid-target.png"
    target.write_bytes(MINIMAL_PNG)
    cache_path = tmp_path / "plantuml-abc.png"
    try:
        cache_path.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlink file tidak didukung: {error}")
    _write_cache_metadata(
        cache_path,
        {
            "format": CACHE_FORMAT,
            "digest": "abc",
            "source_sha256": source_hash,
            "theme": fingerprint,
            "plantuml_version": "1.2026.10",
            "options": _render_options(background),
        },
    )

    result = _find_cached_png(
        tmp_path,
        source_hash=source_hash,
        theme_fingerprint=fingerprint,
        background=background,
    )

    assert result is None
    assert target.read_bytes() == MINIMAL_PNG


def test_find_cached_png_rejects_symlinked_valid_metadata(tmp_path: Path, theme) -> None:
    fingerprint = _theme_fingerprint(theme)
    background = theme.colors.background
    source_hash = "a" * 64
    cache_path = tmp_path / "plantuml-abc.png"
    cache_path.write_bytes(MINIMAL_PNG)
    payload = {
        "format": CACHE_FORMAT,
        "digest": "abc",
        "source_sha256": source_hash,
        "theme": fingerprint,
        "plantuml_version": "1.2026.10",
        "options": _render_options(background),
    }
    target = tmp_path / "valid-target.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    metadata = cache_path.with_suffix(".json")
    try:
        metadata.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlink file tidak didukung: {error}")

    result = _find_cached_png(
        tmp_path,
        source_hash=source_hash,
        theme_fingerprint=fingerprint,
        background=background,
    )

    assert result is None
    assert json.loads(target.read_text(encoding="utf-8")) == payload


TREE_PLANTUML = """\
import os
import pathlib
import subprocess
import sys
import time

if "--version" in sys.argv:
    print("PlantUML version 1.2026.10 (test)")
    raise SystemExit(0)

child_code = (
    "import os, pathlib, time; "
    "pathlib.Path(os.environ['FAKE_PLANTUML_CHILD_READY']).write_text('siap'); "
    "time.sleep(5)"
)
child = subprocess.Popen([sys.executable, "-c", child_code])
pathlib.Path(os.environ["FAKE_PLANTUML_CHILD_PID"]).write_text(
    str(child.pid), encoding="utf-8"
)
time.sleep(5)
"""


def process_running(pid: int) -> bool:
    """True bila proses masih hidup, tanpa mengirim sinyal mematikan."""
    if os.name == "nt":
        synchronize = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x00000102
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_process_exit(pid: int, *, timeout: float = 10.0) -> bool:
    """Tunggu proses berhenti; Windows memakai satu wait bersinyal."""
    if os.name == "nt":
        synchronize = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return True
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, int(timeout * 1000)) == 0
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_running(pid):
            return True
        time.sleep(0.05)
    return False


@pytest.mark.integration
def test_timeout_terminates_child_process_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    script = tmp_path / "tree_plantuml.py"
    script.write_text(TREE_PLANTUML, encoding="utf-8", newline="\n")
    pid_file = tmp_path / "child.pid"
    ready_file = tmp_path / "child.ready"
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(script))
    monkeypatch.setenv("FAKE_PLANTUML_CHILD_PID", str(pid_file))
    monkeypatch.setenv("FAKE_PLANTUML_CHILD_READY", str(ready_file))
    monkeypatch.setattr(plantuml_module, "DEFAULT_TIMEOUT", 2.0)
    source = write_source(tmp_path)
    out = tmp_path / "flow.png"
    child_pid: int | None = None

    try:
        with pytest.raises(PlantUmlError, match="melebihi batas waktu"):
            render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

        assert pid_file.exists()
        assert ready_file.exists()
        child_pid = read_process_id(pid_file)
        assert child_pid is not None
        assert wait_for_process_exit(child_pid), f"child process {child_pid} masih hidup"
        assert not out.exists()
    finally:
        if child_pid is None:
            child_pid = read_process_id(pid_file)
        if child_pid is not None:
            terminate_process(child_pid)

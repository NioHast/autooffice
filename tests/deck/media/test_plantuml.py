"""Tes render PlantUML memakai executable palsu dan kontrak cache PNG."""

import base64
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import autooffice.deck.media.plantuml as plantuml_module
from autooffice.deck.media.plantuml import (
    JAVA_ENV_VAR,
    PLANTUML_ENV_VAR,
    PLANTUML_INSTALL_HINT,
    PNG_SIGNATURE,
    PlantUmlError,
    _copy_png,
    _is_png,
    _validate_png,
    cache_digest,
    find_java,
    find_plantuml,
    plantuml_version,
    render_plantuml,
    resolve_plantuml_source,
)
from autooffice.design.theme import resolve_theme

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
SOURCE_TEXT = "@startuml\nAlice -> Bob: halo\n@enduml\n"
DEFAULT_VERSION = "PlantUML version 1.2026.10 (test)"

FAKE_PLANTUML = """\
import base64
import json
import os
import sys
import time

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

arguments = sys.argv[1:]
log = os.environ.get("FAKE_PLANTUML_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(arguments) + "\\n")

if arguments == ["--version"]:
    if os.environ.get("FAKE_PLANTUML_EMPTY_VERSION"):
        raise SystemExit(0)
    if os.environ.get("FAKE_PLANTUML_VERSION_ERROR"):
        print("fake plantuml: versi gagal dibaca", file=sys.stderr)
        raise SystemExit(2)
    print(os.environ.get("FAKE_PLANTUML_VERSION", "PlantUML version 1.2026.10 (test)"))
    raise SystemExit(0)

source = sys.stdin.buffer.read()
if "--png" not in arguments or "-pipe" not in arguments:
    print("fake plantuml: butuh --png dan -pipe", file=sys.stderr)
    raise SystemExit(2)

if b"!include" in source and "-secure" in arguments:
    print("SecurityException: !include tidak diizinkan", file=sys.stderr)
    raise SystemExit(200)
if os.environ.get("FAKE_PLANTUML_FAIL"):
    print(os.environ["FAKE_PLANTUML_FAIL"], file=sys.stderr)
    raise SystemExit(200)
if os.environ.get("FAKE_PLANTUML_SLEEP"):
    time.sleep(float(os.environ["FAKE_PLANTUML_SLEEP"]))
if os.environ.get("FAKE_PLANTUML_EMPTY_OUTPUT"):
    raise SystemExit(0)
if os.environ.get("FAKE_PLANTUML_INVALID_PNG"):
    sys.stdout.buffer.write(b"bukan png")
    sys.stdout.buffer.flush()
    raise SystemExit(0)

sys.stdout.buffer.write(PNG)
padding = os.environ.get("FAKE_PLANTUML_STDOUT_PADDING")
if padding:
    sys.stdout.buffer.write(b"x" * int(padding))
sys.stdout.buffer.flush()
stderr_bytes = os.environ.get("FAKE_PLANTUML_STDERR_BYTES")
if stderr_bytes:
    sys.stderr.write("x" * int(stderr_bytes))
    sys.stderr.flush()
"""


@pytest.fixture(scope="module")
def theme():
    """Theme indigo untuk render PlantUML."""
    return resolve_theme("indigo")


@pytest.fixture(autouse=True)
def _fresh_version_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolasi cache versi global antar test."""
    monkeypatch.setattr(plantuml_module, "_VERSION_CACHE", {})


def make_fake_plantuml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    version: str = DEFAULT_VERSION,
) -> tuple[Path, Path]:
    """Tulis skrip PlantUML palsu dan aktifkan lewat environment override."""
    log = tmp_path / "plantuml-log.jsonl"
    slug = "".join(character if character.isalnum() else "_" for character in version)
    script = tmp_path / f"fake_plantuml_{slug}.py"
    script.write_text(FAKE_PLANTUML, encoding="utf-8", newline="\n")
    monkeypatch.setenv("FAKE_PLANTUML_LOG", str(log))
    monkeypatch.setenv("FAKE_PLANTUML_VERSION", version)
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(script))
    return script, log


def read_calls(log: Path) -> list[list[str]]:
    """Baca seluruh invocation yang dicatat fake PlantUML."""
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def render_calls(log: Path) -> list[list[str]]:
    """Ambil invocation render, bukan invocation ``--version``."""
    return [call for call in read_calls(log) if "--version" not in call]


def version_calls(log: Path) -> list[list[str]]:
    """Ambil invocation probe versi."""
    return [call for call in read_calls(log) if call == ["--version"]]


def option(arguments: list[str], flag: str) -> str:
    """Ambil nilai satu flag dari daftar argumen."""
    return arguments[arguments.index(flag) + 1]


def write_source(tmp_path: Path, name: str = "flow.puml", text: str = SOURCE_TEXT) -> Path:
    """Tulis sumber PlantUML valid di ``tmp_path``."""
    source = tmp_path / name
    source.write_text(text, encoding="utf-8")
    return source


def cache_pngs(cache: Path) -> list[Path]:
    """Daftar PNG cache PlantUML."""
    return sorted(cache.glob("plantuml-*.png"))


def test_resolve_plantuml_source_accepts_nested_file(tmp_path: Path) -> None:
    diagram = tmp_path / "diagrams" / "arsitektur" / "flow.puml"
    diagram.parent.mkdir(parents=True)
    diagram.write_text(SOURCE_TEXT, encoding="utf-8")

    resolved = resolve_plantuml_source(tmp_path, "diagrams/arsitektur/flow.puml")

    assert resolved == diagram.resolve()


def test_resolve_plantuml_source_accepts_uppercase_extension(tmp_path: Path) -> None:
    diagram = tmp_path / "flow.PUML"
    diagram.write_text(SOURCE_TEXT, encoding="utf-8")

    assert resolve_plantuml_source(tmp_path, "flow.PUML") == diagram.resolve()


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        ("../flow.puml", ".."),
        ("diagrams/../../flow.puml", ".."),
        ("https://example.com/flow.puml", "remote"),
        ("//server/share/flow.puml", "remote"),
        ("\\\\server\\share\\flow.puml", "remote"),
        ("/absolute/flow.puml", "relatif"),
        ("C:/diagrams/flow.puml", "relatif"),
        ("diagrams\\flow.puml", "memakai '/'"),
        ("diagrams//flow.puml", "segmen"),
        ("diagrams/./flow.puml", "segmen"),
        ("diagrams/flow.png", ".puml"),
        ("diagrams/flow", "tanpa ekstensi"),
    ],
)
def test_resolve_plantuml_source_rejects_invalid_paths(
    tmp_path: Path,
    relative: str,
    message: str,
) -> None:
    with pytest.raises(PlantUmlError, match=message) as error:
        resolve_plantuml_source(tmp_path, relative)

    assert error.value.code == "PLANTUML-SOURCE"


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        ("", "kosong"),
        ("diagrams/\x01flow.puml", "kontrol"),
        ("diagrams/\x7fflow.puml", "kontrol"),
        ("hilang.puml", "tidak ditemukan"),
    ],
    ids=["empty", "control", "delete", "missing"],
)
def test_resolve_plantuml_source_rejects_empty_control_and_missing(
    tmp_path: Path,
    relative: str,
    message: str,
) -> None:
    with pytest.raises(PlantUmlError, match=message):
        resolve_plantuml_source(tmp_path, relative)


def test_resolve_plantuml_source_rejects_directory(tmp_path: Path) -> None:
    (tmp_path / "diagram.puml").mkdir()

    with pytest.raises(PlantUmlError, match="tidak ditemukan"):
        resolve_plantuml_source(tmp_path, "diagram.puml")


def test_resolve_plantuml_source_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "deck"
    root.mkdir()
    outside = tmp_path / "luar"
    outside.mkdir()
    (outside / "flow.puml").write_text(SOURCE_TEXT, encoding="utf-8")
    try:
        os.symlink(outside, root / "link", target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink tidak didukung: {error}")

    with pytest.raises(PlantUmlError, match="keluar"):
        resolve_plantuml_source(root, "link/flow.puml")


def test_resolve_plantuml_source_rejects_oversized_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plantuml_module, "MAX_SOURCE_BYTES", 8)
    diagram = tmp_path / "huge.puml"
    diagram.write_text("a" * 9, encoding="utf-8")

    with pytest.raises(PlantUmlError, match="terlalu besar") as error:
        resolve_plantuml_source(tmp_path, "huge.puml")

    assert error.value.code == "PLANTUML-SOURCE"


def test_render_plantuml_passes_flags_and_writes_png(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    out = tmp_path / "out" / "flow.png"

    result = render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert result == out
    assert out.read_bytes() == PNG_1X1
    calls = render_calls(log)
    assert len(calls) == 1
    arguments = calls[0]
    assert "--png" in arguments
    assert "-pipe" in arguments
    assert "-secure" in arguments
    assert "--disable-metadata" in arguments
    assert "--stop-on-error" in arguments
    assert "--no-error-image" in arguments
    assert option(arguments, "--charset") == "UTF-8"
    assert option(arguments, "--threads") == "1"
    assert option(arguments, "--pragma") == "layout=smetana"
    assert option(arguments, "--skinparam") == "dpi=192"
    assert "backgroundColor=" + theme.colors.background in arguments
    assert arguments.count("--skinparam") == 2
    assert "-o" not in arguments


def test_render_plantuml_never_passes_output_path_to_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    out = tmp_path / "rahasia" / "flow.png"

    render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

    arguments = render_calls(log)[0]
    assert str(out) not in arguments
    assert str(out.parent) not in arguments


def test_render_plantuml_background_comes_from_theme(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    alternative = replace(
        theme,
        colors=replace(theme.colors, background="#123456"),
    )

    render_plantuml(source, tmp_path / "flow.png", theme=alternative, cache_dir=tmp_path / "cache")

    arguments = render_calls(log)[0]
    actual = [argument for argument in arguments if argument.startswith("backgroundColor=")]
    assert actual == ["backgroundColor=#123456"]


def test_cache_hit_does_not_render_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    out = tmp_path / "flow.png"
    cache = tmp_path / "cache"

    first = render_plantuml(source, out, theme=theme, cache_dir=cache)
    calls = read_calls(log)
    second = render_plantuml(source, out, theme=theme, cache_dir=cache)

    assert first == second == out
    assert read_calls(log) == calls
    assert len(render_calls(log)) == 1
    assert len(version_calls(log)) == 1
    assert len(cache_pngs(cache)) == 1


def test_deterministic_renders_share_identical_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"
    first_out = tmp_path / "first.png"
    second_out = tmp_path / "second.png"

    render_plantuml(source, first_out, theme=theme, cache_dir=cache)
    render_plantuml(source, second_out, theme=theme, cache_dir=cache)

    assert first_out.read_bytes() == second_out.read_bytes()
    assert first_out.read_bytes() == PNG_1X1
    assert len(render_calls(log)) == 1
    assert len(cache_pngs(cache)) == 1


def test_cache_hit_works_without_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    script, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"
    render_plantuml(source, tmp_path / "first.png", theme=theme, cache_dir=cache)
    calls = read_calls(log)
    script.unlink()
    monkeypatch.delenv(PLANTUML_ENV_VAR, raising=False)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    second_out = tmp_path / "second.png"

    assert find_plantuml() is None
    result = render_plantuml(source, second_out, theme=theme, cache_dir=cache)

    assert result == second_out
    assert second_out.read_bytes() == PNG_1X1
    assert read_calls(log) == calls


def test_cache_first_without_tool_does_not_use_other_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    script, _log = make_fake_plantuml(tmp_path, monkeypatch)
    first_source = write_source(tmp_path, "first.puml", "@startuml\nA -> B\n@enduml\n")
    cache = tmp_path / "cache"
    render_plantuml(first_source, tmp_path / "first.png", theme=theme, cache_dir=cache)
    script.unlink()
    monkeypatch.delenv(PLANTUML_ENV_VAR, raising=False)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    second_source = write_source(tmp_path, "second.puml", "@startuml\nA -> C\n@enduml\n")
    out = tmp_path / "second.png"

    with pytest.raises(PlantUmlError, match="tidak ditemukan") as error:
        render_plantuml(second_source, out, theme=theme, cache_dir=cache)

    assert error.value.code == "PLANTUML-TOOL"
    assert not out.exists()


def test_source_change_invalidates_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"
    out = tmp_path / "flow.png"

    render_plantuml(source, out, theme=theme, cache_dir=cache)
    source.write_text("@startuml\nA -> C\n@enduml\n", encoding="utf-8")
    render_plantuml(source, out, theme=theme, cache_dir=cache)

    assert len(render_calls(log)) == 2
    assert len(cache_pngs(cache)) == 2


def test_theme_and_version_change_invalidate_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"
    out = tmp_path / "flow.png"

    render_plantuml(source, out, theme=theme, cache_dir=cache)
    render_plantuml(source, out, theme=resolve_theme("hitam"), cache_dir=cache)
    make_fake_plantuml(tmp_path, monkeypatch, version="PlantUML version 1.2026.11 (test)")
    render_plantuml(source, out, theme=theme, cache_dir=cache)

    assert len(render_calls(log)) == 3
    assert len(cache_pngs(cache)) == 3


def test_cache_digest_depends_on_theme_and_version(
    tmp_path: Path,
    theme,
) -> None:
    source = write_source(tmp_path)

    indigo = cache_digest(source, theme=theme, plantuml_version="1.2026.10")
    hitam = cache_digest(source, theme=resolve_theme("hitam"), plantuml_version="1.2026.10")
    newer = cache_digest(source, theme=theme, plantuml_version="1.2026.11")

    assert len(indigo) == 64
    assert all(character in "0123456789abcdef" for character in indigo)
    assert len({indigo, hitam, newer}) == 3


def test_cache_digest_matches_written_cache_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, _log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"
    digest = cache_digest(source, theme=theme, plantuml_version="1.2026.10")

    render_plantuml(source, tmp_path / "flow.png", theme=theme, cache_dir=cache)

    assert cache_pngs(cache) == [cache / f"plantuml-{digest}.png"]


def test_cache_sidecar_contains_contract_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, _log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"

    render_plantuml(source, tmp_path / "flow.png", theme=theme, cache_dir=cache)

    sidecars = list(cache.glob("plantuml-*.json"))
    assert len(sidecars) == 1
    payload = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert payload["format"] == plantuml_module.CACHE_FORMAT
    assert payload["digest"] == sidecars[0].stem.removeprefix("plantuml-")
    assert payload["source_sha256"] != payload["digest"]
    assert payload["source_sha256"] == plantuml_module._source_sha256(source)
    assert payload["theme"]["name"] == "indigo"
    assert payload["plantuml_version"] == "1.2026.10"
    assert payload["options"] == {
        "format": "png",
        "dpi": 192,
        "layout": "smetana",
        "background": theme.colors.background,
        "secure": True,
    }


def test_truncated_cache_entry_is_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    digest = cache_digest(source, theme=theme, plantuml_version="1.2026.10")
    cache_path = cache / f"plantuml-{digest}.png"
    cache_path.write_bytes(b"\x89PNG")

    out = tmp_path / "flow.png"
    render_plantuml(source, out, theme=theme, cache_dir=cache)

    assert out.read_bytes() == PNG_1X1
    assert _is_png(cache_path)
    assert len(render_calls(log)) == 1


def test_corrupt_cache_with_metadata_is_rerendered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"
    out = tmp_path / "flow.png"
    render_plantuml(source, out, theme=theme, cache_dir=cache)
    cache_path = cache_pngs(cache)[0]
    sidecar = cache_path.with_suffix(".json")
    assert sidecar.is_file()
    cache_path.write_bytes(PNG_SIGNATURE)

    render_plantuml(source, out, theme=theme, cache_dir=cache)

    assert _is_png(cache_path)
    assert sidecar.is_file()
    assert len(render_calls(log)) == 2


def test_cache_entry_with_only_png_signature_is_rerendered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    digest = cache_digest(source, theme=theme, plantuml_version="1.2026.10")
    cache_path = cache / f"plantuml-{digest}.png"
    cache_path.write_bytes(PNG_SIGNATURE)

    out = tmp_path / "flow.png"
    render_plantuml(source, out, theme=theme, cache_dir=cache)

    assert out.read_bytes() == PNG_1X1
    assert cache_path.read_bytes() == PNG_1X1
    assert len(render_calls(log)) == 1


def test_cache_hit_when_output_is_cache_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    digest = cache_digest(source, theme=theme, plantuml_version="1.2026.10")
    out = cache / f"plantuml-{digest}.png"
    out.write_bytes(PNG_1X1)

    result = render_plantuml(source, out, theme=theme, cache_dir=cache)

    assert result == out
    assert out.read_bytes() == PNG_1X1
    assert render_calls(log) == []


def test_missing_plantuml_override_raises_install_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(tmp_path / "tidak-ada-plantuml.exe"))
    source = write_source(tmp_path)
    out = tmp_path / "flow.png"

    with pytest.raises(PlantUmlError) as error:
        render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

    message = str(error.value)
    assert "PlantUML tidak ditemukan" in message
    assert PLANTUML_INSTALL_HINT in message
    assert error.value.code == "PLANTUML-TOOL"
    assert find_plantuml() is None
    assert not out.exists()


def test_missing_plantuml_without_override_raises_path_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    monkeypatch.delenv(PLANTUML_ENV_VAR, raising=False)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    source = write_source(tmp_path)

    assert find_plantuml() is None
    with pytest.raises(PlantUmlError, match="tidak ditemukan di PATH") as error:
        render_plantuml(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")

    assert PLANTUML_INSTALL_HINT in str(error.value)


def test_plantuml_failure_removes_partial_png(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_FAIL", "syntax error disengaja")
    source = write_source(tmp_path)
    out = tmp_path / "flow.png"

    with pytest.raises(PlantUmlError, match="kode 200") as error:
        render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert "syntax error disengaja" in str(error.value)
    assert error.value.code == "PLANTUML-RENDER"
    assert not out.exists()
    assert cache_pngs(tmp_path / "cache") == []


def test_plantuml_failure_detail_is_truncated_to_tail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_FAIL", "x" * 2500)
    source = write_source(tmp_path)

    with pytest.raises(PlantUmlError) as error:
        render_plantuml(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")

    message = str(error.value)
    assert "x" * 2000 in message
    assert "x" * 2001 not in message


def test_invalid_png_output_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_INVALID_PNG", "1")
    source = write_source(tmp_path)
    out = tmp_path / "flow.png"

    with pytest.raises(PlantUmlError, match="bukan PNG") as error:
        render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert error.value.code == "PLANTUML-OUTPUT"
    assert not out.exists()
    assert cache_pngs(tmp_path / "cache") == []


def test_empty_png_output_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_EMPTY_OUTPUT", "1")
    source = write_source(tmp_path)

    with pytest.raises(PlantUmlError, match="tidak menghasilkan PNG"):
        render_plantuml(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")


def test_oversized_stdout_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setattr(plantuml_module, "MAX_RENDER_BYTES", 16)
    source = write_source(tmp_path)
    out = tmp_path / "flow.png"

    with pytest.raises(PlantUmlError, match="melebihi batas output 16 byte") as error:
        render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert error.value.code == "PLANTUML-RENDER"
    assert not out.exists()


def test_oversized_stderr_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_STDERR_BYTES", str(plantuml_module.MAX_OUTPUT_BYTES + 1))
    source = write_source(tmp_path)
    out = tmp_path / "flow.png"

    with pytest.raises(PlantUmlError, match="melebihi batas output") as error:
        render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert error.value.code == "PLANTUML-RENDER"
    assert not out.exists()


def test_timeout_is_reported_and_removes_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setattr(plantuml_module, "DEFAULT_TIMEOUT", 1.0)
    monkeypatch.setenv("FAKE_PLANTUML_SLEEP", "60")
    source = write_source(tmp_path)
    out = tmp_path / "flow.png"

    with pytest.raises(PlantUmlError, match="melebihi batas waktu") as error:
        render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert error.value.code == "PLANTUML-TIMEOUT"
    assert not out.exists()


def test_render_timeout_removes_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    source, out = _prepare_render_input(tmp_path, monkeypatch)

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if "--version" in command:
            return completed(stdout=DEFAULT_VERSION)
        raise subprocess.TimeoutExpired(command, 180)

    monkeypatch.setattr(plantuml_module, "_run_captured", run)

    with pytest.raises(PlantUmlError, match="melebihi batas waktu"):
        render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert not out.exists()


def test_render_spawn_oserror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    source, out = _prepare_render_input(tmp_path, monkeypatch)

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if "--version" in command:
            return completed(stdout=DEFAULT_VERSION)
        raise OSError("spawn gagal disengaja")

    monkeypatch.setattr(plantuml_module, "_run_captured", run)

    with pytest.raises(PlantUmlError, match="Gagal menjalankan PlantUML") as error:
        render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert error.value.code == "PLANTUML-RENDER"
    assert not out.exists()


def test_render_jar_spawn_oserror_reports_java(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    jar = tmp_path / "plantuml.jar"
    jar.write_bytes(b"")
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(jar))
    monkeypatch.setattr(plantuml_module, "find_java", lambda: Path("java"))
    source = write_source(tmp_path)

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if "--version" in command:
            return completed(stdout=DEFAULT_VERSION)
        raise OSError("java gagal disengaja")

    monkeypatch.setattr(plantuml_module, "_run_captured", run)

    with pytest.raises(PlantUmlError, match="Gagal menjalankan Java") as error:
        render_plantuml(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")

    assert error.value.code == "PLANTUML-JAVA"


def test_render_missing_output_file_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    source, out = _prepare_render_input(tmp_path, monkeypatch)

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if "--version" in command:
            return completed(stdout=DEFAULT_VERSION)
        return completed()

    monkeypatch.setattr(plantuml_module, "_run_captured", run)

    with pytest.raises(PlantUmlError, match="tidak menghasilkan PNG"):
        render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")


def test_render_reports_temporary_directory_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_plantuml(tmp_path, monkeypatch)
    source = write_source(tmp_path)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("temp gagal disengaja")

    monkeypatch.setattr(plantuml_module.tempfile, "TemporaryDirectory", fail)

    with pytest.raises(PlantUmlError, match="Gagal menyiapkan render"):
        render_plantuml(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")


def test_output_must_be_png(tmp_path: Path, theme) -> None:
    source = write_source(tmp_path)

    with pytest.raises(PlantUmlError, match="harus PNG") as error:
        render_plantuml(source, tmp_path / "flow.svg", theme=theme, cache_dir=tmp_path / "cache")

    assert error.value.code == "PLANTUML-OUTPUT"


def test_output_directory_is_rejected(tmp_path: Path, theme) -> None:
    out = tmp_path / "flow.png"
    out.mkdir()
    source = write_source(tmp_path)

    with pytest.raises(PlantUmlError, match="berupa file") as error:
        render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert error.value.code == "PLANTUML-OUTPUT"


def test_render_reports_output_parent_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_plantuml(tmp_path, monkeypatch)
    blocker = tmp_path / "blocker"
    blocker.write_text("bukan folder", encoding="utf-8")
    source = write_source(tmp_path)

    with pytest.raises(PlantUmlError, match="folder output") as error:
        render_plantuml(source, blocker / "flow.png", theme=theme, cache_dir=tmp_path / "cache")

    assert error.value.code == "PLANTUML-OUTPUT"


def test_render_rejects_cache_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_plantuml(tmp_path, monkeypatch)
    cache = tmp_path / "cache"
    cache.write_text("bukan folder", encoding="utf-8")
    source = write_source(tmp_path)

    with pytest.raises(PlantUmlError, match="bukan direktori") as error:
        render_plantuml(source, tmp_path / "flow.png", theme=theme, cache_dir=cache)

    assert error.value.code == "PLANTUML-CACHE"


def test_render_reports_cache_parent_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_plantuml(tmp_path, monkeypatch)
    blocker = tmp_path / "blocker"
    blocker.write_text("bukan folder", encoding="utf-8")
    source = write_source(tmp_path)

    with pytest.raises(PlantUmlError, match="Gagal menyiapkan cache"):
        render_plantuml(
            source,
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=blocker / "cache",
        )


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("../flow.puml", "memuat '..'"),
        ("https://example.com/flow.puml", "remote"),
    ],
)
def test_render_rejects_invalid_source_path(
    source: str,
    message: str,
    tmp_path: Path,
    theme,
) -> None:
    with pytest.raises(PlantUmlError, match=message):
        render_plantuml(
            Path(source),
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )


def test_render_rejects_relative_path_with_drive_separator(
    tmp_path: Path,
    theme,
) -> None:
    with pytest.raises(PlantUmlError, match="drive") as error:
        render_plantuml(
            Path("a:b.puml"),
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )

    assert error.value.code == "PLANTUML-SOURCE"


def test_render_rejects_non_puml_source(tmp_path: Path, theme) -> None:
    with pytest.raises(PlantUmlError, match=r"berekstensi \.puml"):
        render_plantuml(
            Path("flow.svg"),
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )


def test_render_rejects_source_directory(tmp_path: Path, theme) -> None:
    source = tmp_path / "diagram.puml"
    source.mkdir()

    with pytest.raises(PlantUmlError, match="berupa file, bukan direktori"):
        render_plantuml(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")


def test_render_rejects_missing_source(tmp_path: Path, theme) -> None:
    with pytest.raises(PlantUmlError, match="tidak ditemukan"):
        render_plantuml(
            tmp_path / "hilang.puml",
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )


def test_render_rejects_unc_network_path(tmp_path: Path, theme) -> None:
    with pytest.raises(PlantUmlError, match="remote"):
        render_plantuml(
            Path("//server/share/flow.puml"),
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )


def test_render_treats_empty_path_as_non_remote(tmp_path: Path, theme) -> None:
    """``Path()`` tanpa komponen bukan remote dan ditolak karena ekstensi."""
    with pytest.raises(PlantUmlError, match=r"berekstensi \.puml"):
        render_plantuml(
            Path(),
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )


def test_source_over_size_limit_is_rejected(tmp_path: Path, theme) -> None:
    source = tmp_path / "huge.puml"
    source.write_bytes(b"a" * (plantuml_module.MAX_SOURCE_BYTES + 1))

    with pytest.raises(PlantUmlError, match="terlalu besar"):
        render_plantuml(
            source,
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )


def test_plantuml_version_parses_official_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script, log = make_fake_plantuml(tmp_path, monkeypatch)

    assert plantuml_version(script) == "1.2026.10"
    assert version_calls(log) == [["--version"]]


def test_plantuml_version_accepts_bare_version_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script, _log = make_fake_plantuml(tmp_path, monkeypatch, version="1.2026.10")

    assert plantuml_version(script) == "1.2026.10"


def test_plantuml_version_accepts_four_part_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script, _log = make_fake_plantuml(tmp_path, monkeypatch, version="1.2026.10.1")

    assert plantuml_version(script) == "1.2026.10.1"


def test_plantuml_version_is_cached_per_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script, log = make_fake_plantuml(tmp_path, monkeypatch)

    plantuml_version(script)
    plantuml_version(script)

    assert version_calls(log) == [["--version"]]


def test_plantuml_version_rejects_too_old_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script, _log = make_fake_plantuml(
        tmp_path,
        monkeypatch,
        version="PlantUML version 1.2026.9 (test)",
    )

    with pytest.raises(PlantUmlError, match="terlalu lama") as error:
        plantuml_version(script)

    assert error.value.code == "PLANTUML-VERSION"


def test_render_rejects_too_old_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_plantuml(tmp_path, monkeypatch, version="PlantUML version 1.2025.10 (test)")
    source = write_source(tmp_path)

    with pytest.raises(PlantUmlError, match="terlalu lama") as error:
        render_plantuml(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")

    assert error.value.code == "PLANTUML-VERSION"


def test_plantuml_version_rejects_unrecognized_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script, _log = make_fake_plantuml(
        tmp_path,
        monkeypatch,
        version="PlantUML development build",
    )

    with pytest.raises(PlantUmlError, match="tidak melaporkan versi") as error:
        plantuml_version(script)

    assert error.value.code == "PLANTUML-VERSION"


def test_plantuml_version_rejects_empty_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script, _log = make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_EMPTY_VERSION", "1")

    with pytest.raises(PlantUmlError, match="gagal melaporkan versi"):
        plantuml_version(script)


def test_plantuml_version_rejects_nonzero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script, _log = make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_VERSION_ERROR", "1")

    with pytest.raises(PlantUmlError, match="kode 2") as error:
        plantuml_version(script)

    assert "versi gagal dibaca" in str(error.value)


def test_plantuml_version_truncated_output_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "plantuml_truncated.py"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setattr(
        plantuml_module,
        "_run_captured",
        lambda *_args, **_kwargs: completed(stdout=DEFAULT_VERSION, truncated=True),
    )

    with pytest.raises(PlantUmlError, match="batas output"):
        plantuml_version(script)


def test_plantuml_version_timeout_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "plantuml_timeout.py"
    script.write_text("# fake\n", encoding="utf-8")

    def run(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired("plantuml", 30)

    monkeypatch.setattr(plantuml_module, "_run_captured", run)

    with pytest.raises(PlantUmlError, match="melebihi batas waktu") as error:
        plantuml_version(script)

    assert error.value.code == "PLANTUML-TIMEOUT"


def test_plantuml_version_launch_failure_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "plantuml.py"
    script.write_text("# fake\n", encoding="utf-8")

    def run(*_args: object, **_kwargs: object) -> None:
        raise OSError("spawn gagal disengaja")

    monkeypatch.setattr(plantuml_module, "_run_captured", run)

    with pytest.raises(PlantUmlError, match="Gagal membaca versi") as error:
        plantuml_version(script)

    assert error.value.code == "PLANTUML-VERSION"


def test_jar_version_launch_failure_reports_java(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jar = tmp_path / "plantuml.jar"
    jar.write_bytes(b"")
    monkeypatch.setattr(plantuml_module, "find_java", lambda: Path("java"))

    def run(*_args: object, **_kwargs: object) -> None:
        raise OSError("java hilang")

    monkeypatch.setattr(plantuml_module, "_run_captured", run)

    with pytest.raises(PlantUmlError, match="Gagal menjalankan Java") as error:
        plantuml_version(jar)

    assert error.value.code == "PLANTUML-JAVA"


def test_find_plantuml_prefers_env_override(tmp_path: Path, monkeypatch) -> None:
    script = tmp_path / "plantuml"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(script))

    assert find_plantuml() == script.resolve()


def test_find_plantuml_accepts_jar(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "plantuml.jar"
    jar.write_bytes(b"")
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(jar))

    assert find_plantuml() == jar.resolve()


def test_find_plantuml_missing_override_does_not_fall_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "plantuml").write_text("# fake\n", encoding="utf-8")
    (bin_dir / "plantuml.exe").write_bytes(b"")
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(tmp_path / "hilang"))

    assert find_plantuml() is None


def test_find_plantuml_uses_path_fallback(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "plantuml").write_text("# fake\n", encoding="utf-8")
    (bin_dir / "plantuml.exe").write_bytes(b"")
    monkeypatch.delenv(PLANTUML_ENV_VAR, raising=False)
    monkeypatch.setenv("PATH", str(bin_dir))
    found_by_which = shutil.which("plantuml")

    assert found_by_which is not None
    assert find_plantuml() == Path(found_by_which).resolve()


def test_find_java_prefers_env_override(tmp_path: Path, monkeypatch) -> None:
    java = tmp_path / "java-custom"
    java.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv(JAVA_ENV_VAR, str(java))

    assert find_java() == java.resolve()


def test_find_java_missing_override_falls_back_to_java_home(
    tmp_path: Path,
    monkeypatch,
) -> None:
    java = tmp_path / "jdk" / "bin" / ("java.exe" if os.name == "nt" else "java")
    java.parent.mkdir(parents=True)
    java.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv(JAVA_ENV_VAR, str(tmp_path / "hilang"))
    monkeypatch.setenv("JAVA_HOME", str(tmp_path / "jdk"))

    assert find_java() == java.resolve()


def test_find_java_uses_java_home(tmp_path: Path, monkeypatch) -> None:
    java = tmp_path / "jdk" / "bin" / ("java.exe" if os.name == "nt" else "java")
    java.parent.mkdir(parents=True)
    java.write_text("# fake\n", encoding="utf-8")
    monkeypatch.delenv(JAVA_ENV_VAR, raising=False)
    monkeypatch.setenv("JAVA_HOME", str(tmp_path / "jdk"))

    assert find_java() == java.resolve()


def test_find_java_java_home_without_binary_falls_back_to_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    java_home = tmp_path / "jdk"
    (java_home / "bin").mkdir(parents=True)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.delenv(JAVA_ENV_VAR, raising=False)
    monkeypatch.setenv("JAVA_HOME", str(java_home))
    monkeypatch.setenv("PATH", str(empty_bin))

    assert find_java() is None


def test_find_java_uses_path_fallback(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "java").write_text("# fake\n", encoding="utf-8")
    (bin_dir / "java.exe").write_bytes(b"")
    monkeypatch.delenv(JAVA_ENV_VAR, raising=False)
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setenv("PATH", str(bin_dir))
    found_by_which = shutil.which("java")

    assert found_by_which is not None
    assert find_java() == Path(found_by_which).resolve()


def test_find_java_returns_none_when_missing(tmp_path: Path, monkeypatch) -> None:
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.delenv(JAVA_ENV_VAR, raising=False)
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setenv("PATH", str(empty_bin))

    assert find_java() is None


def test_jar_command_prefixes_java_headless(
    tmp_path: Path,
    monkeypatch,
) -> None:
    jar = tmp_path / "plantuml.jar"
    java = tmp_path / "java"
    monkeypatch.setattr(plantuml_module, "find_java", lambda: java)

    command = plantuml_module._plantuml_command(jar, "#FFFFFF")

    assert command[:5] == [str(java), "-Djava.awt.headless=true", "-jar", str(jar), "--png"]
    assert "-pipe" in command
    assert "-secure" in command


def test_jar_without_java_reports_java_error(monkeypatch) -> None:
    monkeypatch.setattr(plantuml_module, "find_java", lambda: None)

    with pytest.raises(PlantUmlError, match="Java tidak ditemukan") as error:
        plantuml_module._plantuml_command(Path("plantuml.jar"), "#FFFFFF")

    assert error.value.code == "PLANTUML-JAVA"


def test_python_wrapper_is_launched_with_current_interpreter() -> None:
    command = plantuml_module._base_command(Path("plantuml.py"))

    assert command == [sys.executable, "plantuml.py"]


def test_binary_executable_is_launched_directly() -> None:
    assert plantuml_module._base_command(Path("plantuml.exe")) == ["plantuml.exe"]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(PNG_SIGNATURE, id="signature-only"),
        pytest.param(PNG_1X1[:-12], id="missing-iend"),
    ],
)
def test_is_png_requires_complete_png(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(payload)

    assert _is_png(path) is False
    with pytest.raises(PlantUmlError, match="bukan PNG"):
        _validate_png(path)


def test_is_png_accepts_complete_png(tmp_path: Path) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(PNG_1X1)

    assert _is_png(path) is True
    _validate_png(path)


def test_copy_png_reports_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(PNG_1X1)
    target = tmp_path / "nested" / "target.png"

    def copyfileobj(_source: object, _target: object) -> None:
        raise OSError("disk penuh")

    monkeypatch.setattr(plantuml_module.shutil, "copyfileobj", copyfileobj)

    with pytest.raises(PlantUmlError, match="Gagal menulis PNG"):
        _copy_png(source, target)

    assert not target.exists()
    assert list(target.parent.glob(".*.tmp")) == []


def test_validate_png_reports_stat_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(PNG_1X1)
    real_stat = Path.stat

    def fail_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == path:
            raise OSError("stat gagal disengaja")
        return real_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", fail_stat)
    monkeypatch.setattr(Path, "is_file", lambda self: self == path)

    with pytest.raises(PlantUmlError, match="tidak dapat dibaca") as error:
        _validate_png(path)

    assert str(path) in str(error.value)


def test_cache_digest_reports_unreadable_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    source = write_source(tmp_path)
    resolved = source.resolve()
    original_open = Path.open

    def open_path(path: Path, *args: object, **kwargs: object):
        if path == resolved:
            raise OSError("izin ditolak")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_path)

    with pytest.raises(PlantUmlError, match="tidak dapat dibaca"):
        cache_digest(source, theme=theme, plantuml_version="1.2026.10")


def test_cache_digest_rejects_invalid_source(tmp_path: Path, theme) -> None:
    with pytest.raises(PlantUmlError, match=r"berekstensi \.puml"):
        cache_digest(tmp_path / "flow.txt", theme=theme, plantuml_version="1.2026.10")


@pytest.mark.integration
@pytest.mark.slow
def test_real_plantuml_renders_high_resolution_png(tmp_path: Path, theme) -> None:
    executable = shutil.which("plantuml")
    jar = shutil.which("plantuml.jar")
    if executable is None and jar is None:
        pytest.skip("PlantUML tidak terpasang")
    source = write_source(tmp_path, text="@startuml\nAlice -> Bob: halo\n@enduml\n")
    out = tmp_path / "flow.png"

    result = render_plantuml(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert result == out
    assert out.read_bytes().startswith(PNG_SIGNATURE)
    with Image.open(out) as image:
        assert max(image.size) >= 1600


def completed(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
    truncated: bool = False,
) -> SimpleNamespace:
    """Hasil proses palsu yang cukup untuk modul PlantUML."""
    return SimpleNamespace(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        truncated=truncated,
    )


def _prepare_render_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    executable = tmp_path / "fake_plantuml.py"
    executable.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(executable))
    source = write_source(tmp_path)
    return source, tmp_path / "flow.png"

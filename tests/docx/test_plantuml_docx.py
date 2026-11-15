"""Tes unit stage PlantUML DOCX: ekstraksi, hash, render, dan stage."""

import base64
import json
import os
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import autooffice.docx.stages.plantuml as plantuml_module
from autooffice.docx.errors import DocgenError, StageError, ToolMissingError
from autooffice.docx.pipeline import ArtifactStore, Workspace
from autooffice.docx.stages.plantuml import (
    PLANTUML_ENV_VAR,
    PlantUmlError,
    PlantUmlStage,
    RenderOptions,
    extract_blocks,
    find_plantuml,
    render_blocks,
    render_hash,
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(payload, zlib.crc32(chunk_type)) & 0xFFFFFFFF
    return len(payload).to_bytes(4, "big") + chunk_type + payload + crc.to_bytes(4, "big")


PNG_IHDR = b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
PNG_HEADER = png_chunk(b"IHDR", PNG_IHDR)
PNG_IDAT = png_chunk(b"IDAT", b"data")
PNG_IEND = png_chunk(b"IEND", b"")
VALID_PNG = PNG_SIGNATURE + PNG_HEADER + PNG_IDAT + PNG_IEND


def png_with_ihdr(ihdr: bytes) -> bytes:
    return PNG_SIGNATURE + png_chunk(b"IHDR", ihdr) + PNG_IDAT + PNG_IEND


CODE_SEQUENCE = "@startuml\nAlice -> Bob: Halo\n@enduml"
CODE_OTHER = "@startuml\nBob -> Alice: Balasan\n@enduml"

FAKE_PLANTUML = """\

import base64
import json
import os
import pathlib
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

if "--version" in arguments:
    print(os.environ.get("FAKE_PLANTUML_VERSION", "PlantUML version 1.2026.10"))
    raise SystemExit(0)

source = sys.stdin.buffer.read()
source_log = os.environ.get("FAKE_PLANTUML_SOURCE_LOG")
if source_log:
    pathlib.Path(source_log).write_bytes(source)

stderr_text = os.environ.get("FAKE_PLANTUML_STDERR")
if stderr_text:
    print(stderr_text, file=sys.stderr)

stderr_size = os.environ.get("FAKE_PLANTUML_STDERR_BYTES")
if stderr_size:
    sys.stderr.write("x" * int(stderr_size))
    sys.stderr.flush()

png_file = os.environ.get("FAKE_PLANTUML_PNG_FILE")
if png_file:
    sys.stdout.buffer.write(pathlib.Path(png_file).read_bytes())
    raise SystemExit(0)

invalid = os.environ.get("FAKE_PLANTUML_INVALID_PNG")
if invalid == "signature":
    sys.stdout.buffer.write(PNG[:8])
    raise SystemExit(0)
if invalid == "truncated":
    sys.stdout.buffer.write(PNG[:-12])
    raise SystemExit(0)
if invalid:
    sys.stdout.buffer.write(b"bukan png")
    raise SystemExit(0)

if os.environ.get("FAKE_PLANTUML_EMPTY"):
    raise SystemExit(0)

sleep_for = os.environ.get("FAKE_PLANTUML_SLEEP")
if sleep_for:
    time.sleep(float(sleep_for))

exit_code = os.environ.get("FAKE_PLANTUML_EXIT")
if exit_code:
    if not os.environ.get("FAKE_PLANTUML_EXIT_EMPTY"):
        sys.stdout.buffer.write(PNG)
    raise SystemExit(int(exit_code))

sys.stdout.buffer.write(PNG)
"""


@pytest.fixture(autouse=True)
def _isolate_plantuml_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bersihkan override engine dan Java agar tes tidak bergantung mesin lokal."""

    for name in (
        PLANTUML_ENV_VAR,
        plantuml_module.JAVA_ENV_VAR,
        plantuml_module.JAVA_HOME_ENV_VAR,
        "FAKE_PLANTUML_LOG",
        "FAKE_PLANTUML_SOURCE_LOG",
        "FAKE_PLANTUML_STDERR",
        "FAKE_PLANTUML_STDERR_BYTES",
        "FAKE_PLANTUML_INVALID_PNG",
        "FAKE_PLANTUML_PNG_FILE",
        "FAKE_PLANTUML_EMPTY",
        "FAKE_PLANTUML_SLEEP",
        "FAKE_PLANTUML_EXIT",
        "FAKE_PLANTUML_EXIT_EMPTY",
        "FAKE_PLANTUML_VERSION",
    ):
        monkeypatch.delenv(name, raising=False)


def plantuml_fence(
    caption: str,
    code: str = CODE_SEQUENCE,
    *,
    newline: str = "\n",
    opener: str = "```",
    closing: str | None = None,
) -> str:
    end = opener if closing is None else closing
    text = f'{opener}{{.plantuml caption="{caption}"}}\n{code.rstrip()}\n{end}\n'
    return text.replace("\n", newline)


def make_fake_plantuml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    name: str = "fake_plantuml.py",
    export_env: bool = True,
) -> tuple[Path, Path]:
    """Tulis executable PlantUML palsu dan aktifkan lewat environment."""

    log = tmp_path / "plantuml-invocations.log"
    monkeypatch.setenv("FAKE_PLANTUML_LOG", str(log))
    script = tmp_path / name
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(FAKE_PLANTUML, encoding="utf-8", newline="\n")
    if export_env:
        monkeypatch.setenv(PLANTUML_ENV_VAR, str(script))
    return script, log


def read_calls(log: Path) -> list[list[str]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def assert_option(arguments: list[str], flag: str, value: str) -> None:
    assert flag in arguments
    assert arguments[arguments.index(flag) + 1] == value


# ---------------------------------------------------------------------------
# Ekstraksi
# ---------------------------------------------------------------------------


def test_plantuml_error_default_code() -> None:
    error = PlantUmlError("gagal")

    assert isinstance(error, DocgenError)
    assert error.code == "PLANTUML"


def test_extract_plantuml_block_positions_and_caption() -> None:
    source = (
        "# BAB I\n\n" + plantuml_fence("Diagram pipeline", CODE_SEQUENCE) + "Setelah diagram.\n"
    )

    blocks = extract_blocks(source, path="bab1.md")

    assert len(blocks) == 1
    block = blocks[0]
    assert block.caption == "Diagram pipeline"
    assert block.code == CODE_SEQUENCE
    assert block.info == '{.plantuml caption="Diagram pipeline"}'
    assert block.line == 3
    assert block.start == 2
    assert block.end == 7
    assert block.indent == ""


def test_extract_ignores_regular_fence() -> None:
    source = "```python\nprint('```{.plantuml caption=\"palsu\"}')\n```\n\n" + plantuml_fence(
        "Diagram asli", CODE_OTHER
    )

    blocks = extract_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].caption == "Diagram asli"
    assert blocks[0].code == CODE_OTHER


@pytest.mark.parametrize(
    ("opener", "closing"),
    [
        ('```{.plantuml caption="Diagram"}', "```"),
        ('```.plantuml caption="Diagram"', "```"),
        ('```plantuml caption="Diagram"', "```"),
        ('```{plantuml caption="Diagram"}', "```"),
        ('```{ .plantuml caption="Diagram" }', "```"),
        ('```plantuml {caption="Diagram"}', "```"),
        ('~~~plantuml caption="Diagram"', "~~~"),
        ('~~~{.plantuml caption="Diagram"}', "~~~"),
    ],
)
def test_extract_info_string_variants(opener: str, closing: str) -> None:
    source = f"{opener}\n{CODE_SEQUENCE}\n{closing}\n"

    blocks = extract_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].caption == "Diagram"


@pytest.mark.parametrize(
    "opener",
    [
        '```{.plantuml caption="Diagram"}',
        '```{.PlantUML caption="Diagram"}',
        '```{.PLANTUML caption="Diagram"}',
        '```.PlantUml caption="Diagram"',
    ],
)
def test_extract_language_is_case_insensitive(opener: str) -> None:
    source = f"{opener}\n{CODE_SEQUENCE}\n```\n"

    blocks = extract_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].caption == "Diagram"


@pytest.mark.parametrize(
    ("opener", "caption"),
    [
        ('```{.plantuml caption="Diagram utama"}', "Diagram utama"),
        ("```{.plantuml caption='Diagram utama'}", "Diagram utama"),
        ('```{.plantuml caption="Diagram \\"kutip\\""}', 'Diagram "kutip"'),
        ("```{.plantuml caption='It\\'s diagram'}", "It's diagram"),
        ('```{.plantuml caption = "Spasi"}', "Spasi"),
        ('```{.plantuml data-caption="Bukan" caption="Asli"}', "Asli"),
        ("```{.plantuml caption='Diagram \"utama\"'}", 'Diagram "utama"'),
    ],
)
def test_extract_caption_quoting(opener: str, caption: str) -> None:
    source = f"{opener}\n{CODE_SEQUENCE}\n```\n"

    blocks = extract_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].caption == caption


def test_extract_fence_length_allows_embedded_triple_backticks() -> None:
    source = '````{.plantuml caption="Panjang"}\n@startuml\nnote "```"\n@enduml\n````\n'

    blocks = extract_blocks(source)

    assert len(blocks) == 1
    assert "```" in blocks[0].code
    assert blocks[0].caption == "Panjang"


def test_extract_longer_closing_fence_is_accepted() -> None:
    source = '````{.plantuml caption="Panjang"}\n@startuml\nA -> B\n@enduml\n`````\n'

    blocks = extract_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].caption == "Panjang"


def test_extract_shorter_closing_fence_does_not_close_block() -> None:
    source = '````{.plantuml caption="Panjang"}\n@startuml\n```\n@enduml\n````\n'

    blocks = extract_blocks(source)

    assert len(blocks) == 1
    assert "```" in blocks[0].code


def test_extract_indentation_is_preserved() -> None:
    source = '  ```{.plantuml caption="Indent"}\n  @startuml\n    Alice -> Bob\n  @enduml\n  ```\n'

    blocks = extract_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].indent == "  "
    assert blocks[0].code == "  @startuml\n    Alice -> Bob\n  @enduml"


def test_extract_multiple_blocks_in_order() -> None:
    source = plantuml_fence("Satu", CODE_SEQUENCE) + "\n" + plantuml_fence("Dua", CODE_OTHER)

    blocks = extract_blocks(source)

    assert [block.caption for block in blocks] == ["Satu", "Dua"]
    assert [block.code for block in blocks] == [CODE_SEQUENCE, CODE_OTHER]
    assert blocks[0].end < blocks[1].start


@pytest.mark.parametrize(
    "source",
    [
        "",
        "# Judul\n\nTeks tanpa diagram.\n",
        "```python\nprint('x')\n```\n",
        "```\n```\n",
        '~~~text\n```{.plantuml caption="palsu"}\n~~~\n',
        '```{.plantuml caption="rusak"\n@startuml\n@enduml\n```\n',
    ],
)
def test_extract_no_blocks_returns_empty(source: str) -> None:
    assert extract_blocks(source) == []


def test_extract_caption_missing_rejected() -> None:
    source = "```{.plantuml}\n@startuml\nA -> B\n@enduml\n```\n"

    with pytest.raises(PlantUmlError) as error:
        extract_blocks(source, path="bab1.md")

    message = str(error.value)
    assert isinstance(error.value, DocgenError)
    assert error.value.code == "PLANTUML-INPUT"
    assert "bab1.md:1" in message
    assert "caption" in message


@pytest.mark.parametrize(
    "opener",
    [
        '```{.plantuml caption=""}',
        "```{.plantuml caption=''}",
        '```{.plantuml caption="   "}',
    ],
)
def test_extract_caption_empty_rejected(opener: str) -> None:
    source = f"{opener}\n{CODE_SEQUENCE}\n```\n"

    with pytest.raises(PlantUmlError, match="caption") as error:
        extract_blocks(source)

    assert error.value.code == "PLANTUML-INPUT"


@pytest.mark.parametrize(
    "body",
    [
        "",
        "\n\n",
        "   \n",
    ],
)
def test_extract_empty_content_rejected(body: str) -> None:
    source = f'```{{.plantuml caption="Diagram"}}\n{body}\n```\n'

    with pytest.raises(PlantUmlError, match="kosong") as error:
        extract_blocks(source)

    assert error.value.code == "PLANTUML-INPUT"


def test_extract_unclosed_plantuml_fence_rejected() -> None:
    source = '```{.plantuml caption="Diagram"}\n@startuml\nA -> B\n'

    with pytest.raises(PlantUmlError, match="tidak ditutup") as error:
        extract_blocks(source)

    assert error.value.code == "PLANTUML-INPUT"


def test_extract_unclosed_regular_fence_is_ignored() -> None:
    source = "```python\nprint('x')\n"

    assert extract_blocks(source) == []


# ---------------------------------------------------------------------------
# Hash dan opsi render
# ---------------------------------------------------------------------------


def test_render_hash_is_stable_for_same_source() -> None:
    digest = render_hash(CODE_SEQUENCE)

    assert len(digest) == 12
    assert digest == render_hash(CODE_SEQUENCE)
    assert digest == render_hash(CODE_SEQUENCE.replace("\n", "\r\n"))
    assert digest == render_hash(CODE_SEQUENCE + "\n\n")
    assert render_hash("   \n\n") == render_hash("")


def test_render_hash_changes_when_source_or_options_change() -> None:
    # Kontrak DOCX: hash PNG hanya memuat sumber ternormalisasi dan RenderOptions;
    # stage tidak memprobe versi engine dan caption hanya menjadi alt text.
    digest = render_hash(CODE_SEQUENCE)

    assert digest != render_hash(CODE_OTHER)
    assert digest != render_hash(CODE_SEQUENCE + "\nnote over Alice: tambahan")
    assert digest != render_hash(CODE_SEQUENCE, RenderOptions(dpi=96))
    assert digest != render_hash(CODE_SEQUENCE, RenderOptions(background="#000000"))
    assert digest == render_hash(CODE_SEQUENCE, RenderOptions())


@pytest.mark.parametrize("dpi", [0, -1, True, 1.5, "192"])
def test_render_options_reject_invalid_dpi(dpi: object) -> None:
    with pytest.raises(ValueError, match="dpi"):
        RenderOptions(dpi=dpi)  # type: ignore[arg-type]


@pytest.mark.parametrize("background", ["", "   ", 1])
def test_render_options_reject_invalid_background(background: object) -> None:
    with pytest.raises(ValueError, match="background"):
        RenderOptions(background=background)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Render blok
# ---------------------------------------------------------------------------


def test_render_blocks_writes_png_and_rewrites_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = (
        "# BAB I\n"
        "\n"
        + plantuml_fence("Diagram pipeline", CODE_SEQUENCE)
        + "\n"
        + plantuml_fence("Diagram kedua", CODE_OTHER)
        + "\nSelesai.\n"
    )

    result = render_blocks(source, base, plantuml=fake_plantuml)

    images = sorted((base / "gambar").glob("plantuml-*.png"))
    assert len(images) == 2
    assert {image.name for image in images} == {
        f"plantuml-{render_hash(CODE_SEQUENCE)}.png",
        f"plantuml-{render_hash(CODE_OTHER)}.png",
    }
    assert all(image.read_bytes() == PNG_1X1 for image in images)
    assert len(read_calls(log)) == 2
    assert "```{.plantuml" not in result
    assert result.count("![") == 2
    assert "Gambar 1.1" not in result
    assert f"![Diagram pipeline](gambar/plantuml-{render_hash(CODE_SEQUENCE)}.png)" in result
    assert f"![Diagram kedua](gambar/plantuml-{render_hash(CODE_OTHER)}.png)" in result
    assert result.startswith("# BAB I\n\n")
    assert result.endswith("Selesai.\n")

    arguments = read_calls(log)[0]
    assert "--png" in arguments
    assert_option(arguments, "--charset", "UTF-8")
    assert_option(arguments, "--threads", "1")
    assert_option(arguments, "--pragma", "layout=smetana")
    assert_option(arguments, "--skinparam", "dpi=192")
    assert "backgroundColor=white" in arguments
    assert "-secure" in arguments
    assert "-pipe" in arguments
    assert "--version" not in arguments
    assert "-o" not in arguments
    assert "--output" not in arguments


def test_render_blocks_sends_source_through_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, log = make_fake_plantuml(tmp_path, monkeypatch)
    source_log = tmp_path / "stdin.bin"
    monkeypatch.setenv("FAKE_PLANTUML_SOURCE_LOG", str(source_log))
    source = plantuml_fence("Diagram pipeline", CODE_SEQUENCE)

    render_blocks(source, base, plantuml=fake_plantuml)

    assert source_log.read_bytes() == (CODE_SEQUENCE + "\n").encode("utf-8")
    assert "-pipe" in read_calls(log)[0]


def test_render_blocks_cache_does_not_call_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = plantuml_fence("Diagram pipeline", CODE_SEQUENCE)

    first = render_blocks(source, base, plantuml=fake_plantuml)
    calls = read_calls(log)
    assert len(calls) == 1

    # Cache harus dipakai tanpa mencari engine sama sekali.
    second = render_blocks(source, base, plantuml=tmp_path / "tidak-ada-plantuml")

    assert second == first
    assert read_calls(log) == calls
    assert len(list((base / "gambar").glob("plantuml-*.png"))) == 1


def test_render_blocks_same_diagram_rendered_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, log = make_fake_plantuml(tmp_path, monkeypatch)
    block = plantuml_fence("Diagram sama", CODE_SEQUENCE)
    source = block + "\n" + block

    result = render_blocks(source, base, plantuml=fake_plantuml)

    assert len(read_calls(log)) == 1
    assert len(list((base / "gambar").glob("plantuml-*.png"))) == 1
    assert result.count("](gambar/plantuml-") == 2


def test_caption_change_updates_alt_text_and_reuses_png(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Caption bukan bagian cache key PNG; perubahan caption hanya mengganti alt text.
    base = tmp_path / "tugas"
    fake_plantuml, log = make_fake_plantuml(tmp_path, monkeypatch)

    first = render_blocks(
        plantuml_fence("Diagram lama", CODE_SEQUENCE),
        base,
        plantuml=fake_plantuml,
    )
    second = render_blocks(
        plantuml_fence("Diagram baru", CODE_SEQUENCE),
        base,
        plantuml=tmp_path / "tidak-ada-plantuml",
    )

    assert "![Diagram lama](" in first
    assert "![Diagram baru](" in second
    assert len(read_calls(log)) == 1
    assert len(list((base / "gambar").glob("plantuml-*.png"))) == 1


def test_render_blocks_without_blocks_does_not_create_folder(tmp_path: Path) -> None:
    base = tmp_path / "tugas"
    source = "# BAB I\n\nTidak ada diagram.\n"

    result = render_blocks(source, base, plantuml=tmp_path / "tidak-ada-plantuml")

    assert result == source
    assert not base.exists()


def test_render_blocks_missing_caption_renders_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = "```{.plantuml}\n@startuml\nA -> B\n@enduml\n```\n"

    with pytest.raises(PlantUmlError, match="caption") as error:
        render_blocks(source, base, plantuml=fake_plantuml)

    assert error.value.code == "PLANTUML-INPUT"
    assert not log.exists()
    assert not (base / "gambar").exists()


def test_render_blocks_passes_path_to_error_message(tmp_path: Path) -> None:
    source = "```{.plantuml}\n@startuml\nA -> B\n@enduml\n```\n"

    with pytest.raises(PlantUmlError) as error:
        render_blocks(source, tmp_path / "tugas", path="bab1.md")

    assert "bab1.md:1" in str(error.value)


def test_render_blocks_missing_engine_raises_tool_missing(tmp_path: Path) -> None:
    base = tmp_path / "tugas"
    source = plantuml_fence("Diagram pipeline", CODE_SEQUENCE)

    with pytest.raises(ToolMissingError) as error:
        render_blocks(source, base, plantuml=tmp_path / "tidak-ada-plantuml")

    message = str(error.value)
    assert isinstance(error.value, DocgenError)
    assert error.value.tool == "plantuml"
    assert error.value.code == "TOOL-MISSING"
    assert error.value.exit_code == 1
    assert "PlantUML tidak ditemukan" in message
    assert PLANTUML_ENV_VAR in message
    assert "plantuml.jar" in message
    assert not (base / "gambar").exists()


def test_missing_engine_with_empty_environment_falls_back_to_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(PLANTUML_ENV_VAR, "")
    monkeypatch.setattr(plantuml_module.shutil, "which", lambda name: None)

    with pytest.raises(ToolMissingError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            tmp_path / "tugas",
        )

    assert "tidak ditemukan di PATH" in str(error.value)


def test_empty_environment_uses_fake_plantuml_from_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    script, log = make_fake_plantuml(tmp_path, monkeypatch, export_env=False)
    monkeypatch.setenv(PLANTUML_ENV_VAR, "")
    monkeypatch.setattr(
        plantuml_module.shutil,
        "which",
        lambda name: str(script) if name == "plantuml" else None,
    )

    result = render_blocks(plantuml_fence("Diagram pipeline", CODE_SEQUENCE), base)

    images = list((base / "gambar").glob("plantuml-*.png"))
    assert len(images) == 1
    assert images[0].read_bytes() == PNG_1X1
    assert "](gambar/plantuml-" in result
    assert len(read_calls(log)) == 1


def test_missing_engine_with_invalid_environment_explained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(tmp_path / "tidak-ada-plantuml"))

    with pytest.raises(ToolMissingError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            tmp_path / "tugas",
        )

    message = str(error.value)
    assert "menunjuk path" in message
    assert PLANTUML_ENV_VAR in message


def test_missing_engine_without_environment_explained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(PLANTUML_ENV_VAR, raising=False)
    monkeypatch.setattr(plantuml_module.shutil, "which", lambda name: None)

    with pytest.raises(ToolMissingError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            tmp_path / "tugas",
        )

    assert "tidak ditemukan di PATH" in str(error.value)


@pytest.mark.parametrize(
    ("exit_code", "expected_code", "expected_text"),
    [
        (200, "PLANTUML-SYNTAX", "kesalahan sintaks"),
        (50, "PLANTUML-NO-DIAGRAM", "tidak ada diagram"),
        (3, "PLANTUML-FAILED", "kode 3"),
    ],
)
def test_render_failure_reports_specific_error_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
    expected_code: str,
    expected_text: str,
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, log = make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_EXIT", str(exit_code))
    monkeypatch.setenv("FAKE_PLANTUML_STDERR", "detail kegagalan")

    with pytest.raises(PlantUmlError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=fake_plantuml,
        )

    message = str(error.value)
    assert error.value.code == expected_code
    assert expected_text in message
    assert "detail kegagalan" in message
    assert len(read_calls(log)) == 1
    assert list((base / "gambar").glob("plantuml-*.png")) == []


def test_render_failure_uses_stdout_detail_when_stderr_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_EXIT", "3")

    with pytest.raises(PlantUmlError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=fake_plantuml,
        )

    assert error.value.code == "PLANTUML-FAILED"
    assert "kode 3" in str(error.value)
    assert list((base / "gambar").glob("plantuml-*.png")) == []


def test_render_failure_without_detail_keeps_clean_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_EXIT", "3")
    monkeypatch.setenv("FAKE_PLANTUML_EXIT_EMPTY", "1")

    with pytest.raises(PlantUmlError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=fake_plantuml,
        )

    message = str(error.value)
    assert error.value.code == "PLANTUML-FAILED"
    assert "kode 3" in message
    assert not message.endswith(":")
    assert list((base / "gambar").glob("plantuml-*.png")) == []


def test_render_timeout_reports_timeout_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_SLEEP", "30")

    with pytest.raises(PlantUmlError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=fake_plantuml,
            timeout=1,
        )

    assert error.value.code == "PLANTUML-TIMEOUT"
    assert "melebihi batas waktu 1 detik" in str(error.value)
    assert list((base / "gambar").glob("plantuml-*.png")) == []


@pytest.mark.parametrize("mode", ["raw", "signature", "truncated"])
def test_render_invalid_png_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_INVALID_PNG", mode)

    with pytest.raises(PlantUmlError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=fake_plantuml,
        )

    assert error.value.code == "PLANTUML-OUTPUT"
    assert "bukan PNG valid" in str(error.value)
    assert list((base / "gambar").glob("plantuml-*.png")) == []


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        pytest.param(PNG_SIGNATURE, "IEND tidak ditemukan", id="signature-only"),
        pytest.param(
            PNG_SIGNATURE + PNG_HEADER,
            "IEND tidak ditemukan",
            id="header-only",
        ),
        pytest.param(
            VALID_PNG[:-1] + bytes([VALID_PNG[-1] ^ 1]),
            "CRC chunk IEND rusak",
            id="bad-crc",
        ),
        pytest.param(VALID_PNG[:-2], "CRC terpotong", id="crc-truncated"),
        pytest.param(VALID_PNG + b"x", "data setelah IEND", id="data-after-iend"),
        pytest.param(
            PNG_SIGNATURE + PNG_HEADER + PNG_HEADER + PNG_IDAT + PNG_IEND,
            "IHDR ganda",
            id="duplicate-ihdr",
        ),
        pytest.param(
            PNG_SIGNATURE
            + png_chunk(
                b"IHDR",
                b"\x00\x00\x00\x00\x00\x00\x00\x01\x08\x06\x00\x00\x00",
            )
            + PNG_IDAT
            + PNG_IEND,
            "dimensi IHDR nol",
            id="zero-dimensions",
        ),
        pytest.param(
            PNG_SIGNATURE + PNG_HEADER + PNG_IEND,
            "IDAT tidak ditemukan",
            id="missing-idat",
        ),
        pytest.param(
            PNG_SIGNATURE + PNG_HEADER + PNG_IDAT + png_chunk(b"IEND", b"x"),
            "IEND tidak valid",
            id="iend-payload",
        ),
        pytest.param(
            PNG_SIGNATURE + (0).to_bytes(4, "big") + b"1234" + (0).to_bytes(4, "big"),
            "tipe chunk tidak valid",
            id="bad-chunk-type",
        ),
        pytest.param(
            PNG_SIGNATURE + png_chunk(b"IHDR", b"x"),
            "IHDR tidak valid",
            id="bad-ihdr-length",
        ),
        pytest.param(
            PNG_SIGNATURE + b"\x00\x00\x00\x0dIHDR",
            "chunk terpotong",
            id="truncated-chunk",
        ),
        pytest.param(
            PNG_SIGNATURE + b"\x00\x00\x00",
            "chunk terpotong",
            id="short-chunk-header",
        ),
        pytest.param(
            PNG_SIGNATURE + (0x80000000).to_bytes(4, "big") + b"IHDR" + (0).to_bytes(4, "big"),
            "panjang chunk tidak valid",
            id="oversized-chunk",
        ),
    ],
)
def test_render_rejects_structurally_invalid_png(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    reason: str,
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    png_file = tmp_path / "payload.png"
    png_file.write_bytes(payload)
    monkeypatch.setenv("FAKE_PLANTUML_PNG_FILE", str(png_file))

    with pytest.raises(PlantUmlError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=fake_plantuml,
        )

    assert error.value.code == "PLANTUML-OUTPUT"
    assert reason in str(error.value)
    assert list((base / "gambar").glob("plantuml-*.png")) == []


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        pytest.param(
            png_with_ihdr(PNG_IHDR[:9] + b"\x01" + PNG_IHDR[10:]),
            "color type IHDR tidak valid",
            id="bad-color-type",
        ),
        pytest.param(
            png_with_ihdr(PNG_IHDR[:8] + b"\x04" + PNG_IHDR[9:]),
            "bit depth IHDR tidak valid",
            id="bad-bit-depth",
        ),
        pytest.param(
            png_with_ihdr(PNG_IHDR[:10] + b"\x01" + PNG_IHDR[11:]),
            "compression IHDR tidak valid",
            id="bad-compression",
        ),
        pytest.param(
            png_with_ihdr(PNG_IHDR[:11] + b"\x01" + PNG_IHDR[12:]),
            "filter IHDR tidak valid",
            id="bad-filter",
        ),
        pytest.param(
            png_with_ihdr(PNG_IHDR[:12] + b"\x02" + PNG_IHDR[13:]),
            "interlace IHDR tidak valid",
            id="bad-interlace",
        ),
        pytest.param(
            VALID_PNG[:-1] + bytes([VALID_PNG[-1] ^ 1]),
            "CRC chunk IEND rusak",
            id="bad-crc",
        ),
        pytest.param(
            PNG_SIGNATURE + PNG_HEADER + PNG_IDAT,
            "IEND tidak ditemukan",
            id="missing-iend",
        ),
    ],
)
def test_existing_invalid_png_is_rerendered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    reason: str,
) -> None:
    base = tmp_path / "tugas"
    image_path = base / "gambar" / f"plantuml-{render_hash(CODE_SEQUENCE)}.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(payload)
    fake_plantuml, log = make_fake_plantuml(tmp_path, monkeypatch)

    result = render_blocks(
        plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
        base,
        plantuml=fake_plantuml,
    )

    assert image_path.read_bytes() == PNG_1X1, reason
    assert len(read_calls(log)) == 1
    assert f"](gambar/{image_path.name})" in result


def test_existing_invalid_png_without_engine_is_rejected(tmp_path: Path) -> None:
    base = tmp_path / "tugas"
    image_path = base / "gambar" / f"plantuml-{render_hash(CODE_SEQUENCE)}.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(PNG_SIGNATURE + PNG_HEADER + PNG_IDAT)

    with pytest.raises(ToolMissingError):
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=tmp_path / "tidak-ada-plantuml",
        )

    assert not image_path.exists()


def test_render_empty_stdout_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_EMPTY", "1")

    with pytest.raises(PlantUmlError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=fake_plantuml,
        )

    assert error.value.code == "PLANTUML-OUTPUT"
    assert "tidak menghasilkan PNG" in str(error.value)
    assert list((base / "gambar").glob("plantuml-*.png")) == []


def test_render_oversized_stderr_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PLANTUML_STDERR_BYTES", str(64 * 1024 + 1))

    with pytest.raises(PlantUmlError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=fake_plantuml,
        )

    assert error.value.code == "PLANTUML-OUTPUT"
    assert "Output stderr PlantUML melebihi batas" in str(error.value)
    assert list((base / "gambar").glob("plantuml-*.png")) == []


def test_render_oversized_output_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setattr(plantuml_module, "MAX_OUTPUT_BYTES", 10)

    with pytest.raises(PlantUmlError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=fake_plantuml,
        )

    assert error.value.code == "PLANTUML-OUTPUT"
    assert "melebihi batas 10 byte" in str(error.value)
    assert list((base / "gambar").glob("plantuml-*.png")) == []


def test_render_exec_failure_reports_exec_code(tmp_path: Path) -> None:
    base = tmp_path / "tugas"
    broken = tmp_path / "plantuml.exe"
    broken.write_text("bukan executable", encoding="utf-8")

    with pytest.raises(PlantUmlError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=broken,
        )

    assert error.value.code == "PLANTUML-EXEC"
    assert "Gagal menjalankan PlantUML" in str(error.value)
    assert list((base / "gambar").glob("plantuml-*.png")) == []


def test_jar_without_java_raises_tool_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    jar = tmp_path / "plantuml.jar"
    jar.write_bytes(b"PK")
    monkeypatch.setattr(plantuml_module, "_find_java", lambda: None)

    with pytest.raises(ToolMissingError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=jar,
        )

    assert error.value.tool == "java"
    assert error.value.code == "PLANTUML-JAVA"
    assert "Java tidak ditemukan" in str(error.value)
    assert plantuml_module.JAVA_ENV_VAR in str(error.value)
    assert list((base / "gambar").glob("plantuml-*.png")) == []


def test_jar_command_uses_java_headless_and_jar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    java = tmp_path / "java"
    java.write_text("", encoding="utf-8")
    monkeypatch.setenv(plantuml_module.JAVA_ENV_VAR, str(java))

    command = plantuml_module._plantuml_command("plantuml.jar", RenderOptions())

    assert command[:4] == [str(java), "-Djava.awt.headless=true", "-jar", "plantuml.jar"]
    assert "-secure" in command
    assert "-pipe" in command


def test_find_java_from_java_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "jdk"
    executable = "java.exe" if os.name == "nt" else "java"
    candidate = home / "bin" / executable
    candidate.parent.mkdir(parents=True)
    candidate.write_text("", encoding="utf-8")
    monkeypatch.delenv(plantuml_module.JAVA_ENV_VAR, raising=False)
    monkeypatch.setenv(plantuml_module.JAVA_HOME_ENV_VAR, str(home))

    assert plantuml_module._find_java() == str(candidate)


def test_render_blocks_path_with_spaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "tugas akhir" / "gambar diagram"
    fake_plantuml, _log = make_fake_plantuml(
        tmp_path / "tool plantuml",
        monkeypatch,
        name="fake plantuml.py",
    )
    source = plantuml_fence("Diagram pipeline", CODE_SEQUENCE)

    result = render_blocks(source, base, plantuml=fake_plantuml)

    images = list((base / "gambar").glob("plantuml-*.png"))
    assert len(images) == 1
    assert images[0].read_bytes() == PNG_1X1
    assert f"](gambar/{images[0].name})" in result


def test_render_blocks_passes_options_and_changes_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, log = make_fake_plantuml(tmp_path, monkeypatch)
    source = plantuml_fence("Diagram pipeline", CODE_SEQUENCE)
    options = RenderOptions(dpi=96, background="#EEEEEE")

    result = render_blocks(source, base, plantuml=fake_plantuml, options=options)

    calls = read_calls(log)
    assert len(calls) == 1
    assert_option(calls[0], "--skinparam", "dpi=96")
    assert "backgroundColor=#EEEEEE" in calls[0]
    first_images = list((base / "gambar").glob("plantuml-*.png"))
    assert len(first_images) == 1
    assert first_images[0].name in result

    # Opsi berbeda harus menghasilkan hash dan PNG berbeda.
    other = render_blocks(source, base, plantuml=fake_plantuml)
    other_images = list((base / "gambar").glob("plantuml-*.png"))
    assert len(other_images) == 2
    assert len(read_calls(log)) == 2
    assert other != result


def test_render_blocks_base_dir_file_rejected(tmp_path: Path) -> None:
    base = tmp_path / "tugas"
    base.write_text("berkas", encoding="utf-8")

    with pytest.raises(PlantUmlError, match="bukan direktori") as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=tmp_path / "tidak-ada-plantuml",
        )

    assert error.value.code == "PLANTUML-OUTPUT"


def test_render_blocks_mkdir_failure_reports_output_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("berkas", encoding="utf-8")
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)

    with pytest.raises(PlantUmlError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            blocker / "tugas",
            plantuml=fake_plantuml,
        )

    assert error.value.code == "PLANTUML-OUTPUT"
    assert "Gagal menyiapkan folder gambar" in str(error.value)


def test_render_write_failure_reports_output_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)

    def fail_write(self: Path, data: bytes) -> int:
        raise OSError("disk penuh")

    monkeypatch.setattr(Path, "write_bytes", fail_write)

    with pytest.raises(PlantUmlError) as error:
        render_blocks(
            plantuml_fence("Diagram pipeline", CODE_SEQUENCE),
            base,
            plantuml=fake_plantuml,
        )

    assert error.value.code == "PLANTUML-OUTPUT"
    assert "Gagal menulis PNG PlantUML" in str(error.value)
    assert list((base / "gambar").glob("plantuml-*.png")) == []


def test_line_ending_crlf_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    source = (
        "# BAB I\r\n"
        "\r\n"
        + plantuml_fence("Diagram pipeline", CODE_SEQUENCE, newline="\r\n")
        + "\r\nSesudah.\r\n"
    )

    result = render_blocks(source, base, plantuml=fake_plantuml)

    assert "](gambar/plantuml-" in result
    assert "\n" not in result.replace("\r\n", "")


def test_line_ending_cr_only_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    source = (
        "# BAB I\r\r"
        + plantuml_fence("Diagram pipeline", CODE_SEQUENCE, newline="\r")
        + "\rSesudah.\r"
    )

    result = render_blocks(source, base, plantuml=fake_plantuml)

    assert "](gambar/plantuml-" in result
    assert "\n" not in result


def test_without_trailing_newline_stays_without_newline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    source = plantuml_fence("Diagram pipeline", CODE_SEQUENCE).removesuffix("\n")

    result = render_blocks(source, base, plantuml=fake_plantuml)

    assert result.startswith("![Diagram pipeline](gambar/plantuml-")
    assert not result.endswith("\n")


def test_fence_indentation_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    source = '  ```{.plantuml caption="Diagram"}\n  @startuml\n    A -> B\n  @enduml\n  ```\n'

    result = render_blocks(source, base, plantuml=fake_plantuml)

    assert result.startswith("  ![Diagram](gambar/plantuml-")


def test_caption_with_square_brackets_escaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    source = plantuml_fence("Diagram [utama]", CODE_SEQUENCE)

    result = render_blocks(source, base, plantuml=fake_plantuml)

    assert result.startswith("![Diagram [utama\\]](gambar/plantuml-")


def test_caption_backslash_escaped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "tugas"
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    source = '```{.plantuml caption="Diagram \\ utama"}\n' + CODE_SEQUENCE + "\n```\n"

    result = render_blocks(source, base, plantuml=fake_plantuml)

    assert result.startswith("![Diagram \\\\ utama](gambar/plantuml-")


def test_find_plantuml_explicit_env_and_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "plantuml"
    script.write_text("", encoding="utf-8")

    assert find_plantuml(script) == str(script)
    assert find_plantuml(tmp_path / "tidak-ada-plantuml") is None

    monkeypatch.setenv(PLANTUML_ENV_VAR, str(script))
    assert find_plantuml() == str(script)

    monkeypatch.setenv(PLANTUML_ENV_VAR, "   ")
    monkeypatch.setattr(plantuml_module.shutil, "which", lambda name: None)
    assert find_plantuml() is None

    monkeypatch.setenv(PLANTUML_ENV_VAR, str(tmp_path / "tidak-ada-plantuml"))
    assert find_plantuml() is None


@pytest.mark.parametrize("value", [None, ""], ids=["unset", "empty"])
def test_find_plantuml_uses_path_when_environment_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv(PLANTUML_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(PLANTUML_ENV_VAR, value)
    monkeypatch.setattr(
        plantuml_module.shutil,
        "which",
        lambda name: "plantuml-dari-path" if name == "plantuml" else None,
    )

    assert find_plantuml() == "plantuml-dari-path"


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------


def _stage_context(tmp_path: Path, body: str) -> SimpleNamespace:
    return SimpleNamespace(
        document=SimpleNamespace(body=body, path=Path("document.md")),
        workspace=Workspace(root=tmp_path / ".laporan-build", keep=True),
        artifacts=ArtifactStore(),
    )


def test_stage_without_blocks_still_writes_plantuml_md_and_artifact(tmp_path: Path) -> None:
    body = "# BAB I\n\nTidak ada diagram.\n"
    ctx = _stage_context(tmp_path, body)

    first = PlantUmlStage().run(ctx)

    output = ctx.workspace.path("plantuml.md")
    assert first.stage == "plantuml"
    assert first.status == "ok"
    assert first.changed is True
    assert first.metrics["blocks"] == 0
    assert first.artifacts == (output,)
    assert output.read_text(encoding="utf-8") == body
    assert not (ctx.workspace.root / "gambar").exists()
    assert ctx.artifacts.get("plantuml.markdown") == output

    second = PlantUmlStage().run(ctx)

    assert second.status == "ok"
    assert second.changed is False
    assert second.metrics["blocks"] == 0
    assert ctx.artifacts.get("plantuml.markdown") == output


def test_stage_renders_blocks_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_plantuml, log = make_fake_plantuml(tmp_path, monkeypatch)
    body = (
        "# BAB I\n\n"
        + plantuml_fence("Diagram pipeline", CODE_SEQUENCE)
        + "\n"
        + plantuml_fence("Diagram kedua", CODE_OTHER)
        + "\nSelesai.\n"
    )
    ctx = _stage_context(tmp_path, body)

    first = PlantUmlStage().run(ctx)

    output = ctx.workspace.path("plantuml.md")
    text = output.read_text(encoding="utf-8")
    assert first.status == "ok"
    assert first.changed is True
    assert first.metrics["blocks"] == 2
    assert first.artifacts == (output,)
    assert ctx.artifacts.get("plantuml.markdown") == output
    assert "```{.plantuml" not in text
    assert text.count("](gambar/plantuml-") == 2
    assert len(list((ctx.workspace.root / "gambar").glob("plantuml-*.png"))) == 2
    assert len(read_calls(log)) == 2

    second = PlantUmlStage().run(ctx)

    assert second.status == "ok"
    assert second.changed is False
    assert second.metrics["blocks"] == 2
    assert output.read_text(encoding="utf-8") == text
    assert len(read_calls(log)) == 2
    assert fake_plantuml.is_file()


def test_stage_missing_document_raises_domain_error(tmp_path: Path) -> None:
    ctx = SimpleNamespace(
        workspace=Workspace(root=tmp_path / ".laporan-build", keep=True),
        artifacts=ArtifactStore(),
    )

    with pytest.raises(StageError) as error:
        PlantUmlStage().run(ctx)

    assert error.value.code == "PLANTUML-NO-DOCUMENT"
    assert not ctx.workspace.path("plantuml.md").exists()


def test_stage_missing_workspace_raises_plantuml_error(tmp_path: Path) -> None:
    ctx = SimpleNamespace(
        document=SimpleNamespace(body="# BAB I\n\nTidak ada diagram.\n", path=Path("document.md")),
        artifacts=ArtifactStore(),
    )

    with pytest.raises(PlantUmlError) as error:
        PlantUmlStage().run(ctx)

    assert error.value.code == "PLANTUML-WORKSPACE"
    assert "workspace" in str(error.value)


def test_stage_input_error_uses_plantuml_input_code(tmp_path: Path) -> None:
    body = "```{.plantuml}\n@startuml\nA -> B\n@enduml\n```\n"
    ctx = _stage_context(tmp_path, body)

    with pytest.raises(PlantUmlError) as error:
        PlantUmlStage().run(ctx)

    assert error.value.code == "PLANTUML-INPUT"
    assert not ctx.workspace.path("plantuml.md").exists()


@pytest.mark.parametrize(
    ("variable", "value", "expected_code"),
    [
        ("FAKE_PLANTUML_EXIT", "200", "PLANTUML-SYNTAX"),
        ("FAKE_PLANTUML_EXIT", "50", "PLANTUML-NO-DIAGRAM"),
        ("FAKE_PLANTUML_EXIT", "3", "PLANTUML-FAILED"),
        ("FAKE_PLANTUML_INVALID_PNG", "raw", "PLANTUML-OUTPUT"),
    ],
)
def test_stage_render_error_uses_plantuml_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
    expected_code: str,
) -> None:
    fake_plantuml, _log = make_fake_plantuml(tmp_path, monkeypatch)
    monkeypatch.setenv(variable, value)
    ctx = _stage_context(
        tmp_path,
        "# BAB I\n\n" + plantuml_fence("Diagram pipeline", CODE_SEQUENCE) + "\n",
    )

    with pytest.raises(PlantUmlError) as error:
        PlantUmlStage().run(ctx)

    assert error.value.code == expected_code
    assert not ctx.workspace.path("plantuml.md").exists()
    assert list((ctx.workspace.root / "gambar").glob("plantuml-*.png")) == []
    assert fake_plantuml.is_file()


def test_stage_missing_engine_raises_tool_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(tmp_path / "tidak-ada-plantuml"))
    ctx = _stage_context(
        tmp_path,
        "# BAB I\n\n" + plantuml_fence("Diagram pipeline", CODE_SEQUENCE) + "\n",
    )

    with pytest.raises(ToolMissingError) as error:
        PlantUmlStage().run(ctx)

    assert error.value.tool == "plantuml"
    assert error.value.code == "TOOL-MISSING"
    assert not ctx.workspace.path("plantuml.md").exists()


def test_stage_wraps_unexpected_render_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_render(*args: object, **kwargs: object) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(plantuml_module, "render_blocks", fail_render)
    ctx = _stage_context(tmp_path, "# BAB I\n\nTidak ada diagram.\n")

    with pytest.raises(StageError) as error:
        PlantUmlStage().run(ctx)

    assert error.value.code == "PLANTUML-STAGE"
    assert isinstance(error.value.cause, RuntimeError)
    assert "stage plantuml gagal" in str(error.value)

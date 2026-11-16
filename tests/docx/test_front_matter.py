"""Tes unit stage ``front_matter`` setelah front matter pindah ke Markdown."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from autooffice.docx.config import load_format, load_structure
from autooffice.docx.document import Document
from autooffice.docx.markdown.headings import LINE_BREAK
from autooffice.docx.metadata import normalize_metadata
from autooffice.docx.pipeline import ArtifactStore, Workspace
from autooffice.docx.stages.front_matter import (
    SECTION_BREAK_MARKER,
    FrontMatterError,
    FrontMatterStage,
    render_front_matter,
    section_break,
)
from autooffice.docx.stages.plantuml import PlantUmlStage

_TITLE = "Optimasi Pipeline Pemrosesan Dokumen Markdown untuk Laporan Tugas Akhir"
_PAGE_BREAK_XML = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
_BODY = (
    '::: {custom-style="CoverTitle"}\n'
    "JUDUL SAMPUL\n"
    ":::\n\n"
    f"{SECTION_BREAK_MARKER}\n\n"
    "# LEMBAR PENGESAHAN {-}\n\n"
    "Isi lembar pengesahan.\n\n"
    "```{=openxml}\n"
    f"{_PAGE_BREAK_XML}\n"
    "```\n\n"
    "# Pendahuluan\n\n"
    "Teks pendahuluan.\n\n"
    "## Latar Belakang\n\n"
    "Teks latar belakang.\n\n"
    "### Detail\n\n"
    "Teks detail.\n"
)

_BASE_FRONT_MATTER: dict[str, Any] = {
    "title": _TITLE,
    "author": "Nama Mahasiswa",
    "nim": "30000000000000",
    "lang": "id-ID",
    "report_name": "Tugas",
}


def _document(
    front_matter: dict[str, Any] | None = None,
    *,
    body: str = _BODY,
    structure_id: str = "thesis",
) -> Document:
    values = dict(_BASE_FRONT_MATTER)
    if front_matter:
        values.update(front_matter)
    metadata = normalize_metadata(values, source="test")
    return Document(
        path=Path("document.md"),
        front_matter=values,
        body=body,
        metadata=metadata,
        structure_id=structure_id,
        format_id="undip-msi",
        bibliography=None,
        body_start=9,
    )


def _render(
    *,
    body: str = _BODY,
    structure_id: str = "thesis",
    page_overrides: dict[str, Any] | None = None,
) -> str:
    format_ = load_format("undip-msi")
    if page_overrides:
        format_ = replace(format_, page=replace(format_.page, **page_overrides))
    return render_front_matter(
        body,
        format_,
        numbering_body=load_structure(structure_id).numbering.body,
    )


def test_section_break_uses_format_yaml_margins() -> None:
    output = _render()

    assert 'w:top="2268"' in output
    assert 'w:right="1701"' in output
    assert 'w:bottom="1701"' in output
    assert 'w:left="2268"' in output
    assert 'w:header="720"' in output
    assert 'w:footer="720"' in output
    assert 'w:top="1134"' not in output
    assert 'w:right="1417"' not in output


def test_section_break_normalizes_legacy_size_alias() -> None:
    portrait = _render(page_overrides={"size": "LETTER", "orientation": "portrait"})
    assert 'w:w="12240"' in portrait
    assert 'w:h="15840"' in portrait
    assert 'w:orient="landscape"' not in portrait

    landscape = _render(page_overrides={"size": "LETTER", "orientation": "landscape"})
    assert 'w:w="15840"' in landscape
    assert 'w:h="12240"' in landscape
    assert 'w:orient="landscape"' in landscape

    lowercase = _render(page_overrides={"size": "a4", "orientation": "portrait"})
    assert 'w:w="11906"' in lowercase
    assert 'w:h="16838"' in lowercase


@pytest.mark.parametrize(
    ("size", "orientation"),
    [
        ("A5", "portrait"),
        ("A4", "diagonal"),
    ],
)
def test_section_break_rejects_invalid_size_or_orientation(
    size: str,
    orientation: str,
) -> None:
    with pytest.raises(FrontMatterError) as excinfo:
        _render(page_overrides={"size": size, "orientation": orientation})

    assert excinfo.value.code == "FRONT-MATTER-PAGE"
    assert size in str(excinfo.value)
    assert orientation in str(excinfo.value)


def test_marker_replaced_by_raw_openxml() -> None:
    output = _render()

    assert SECTION_BREAK_MARKER not in output
    assert output.count("```{=openxml}") == 2
    assert "<w:sectPr>" in output


def test_every_marker_is_replaced() -> None:
    body = f"{SECTION_BREAK_MARKER}\n\nteks\n\n{SECTION_BREAK_MARKER}\n"
    output = render_front_matter(body, load_format("undip-msi"))

    assert SECTION_BREAK_MARKER not in output
    assert output.count("<w:sectPr>") == 2


def test_marker_without_surrounding_blank_lines_is_replaced() -> None:
    body = f"sebelum\n{SECTION_BREAK_MARKER}\nsesudah\n"
    output = render_front_matter(body, load_format("undip-msi"))

    assert "sebelum" in output
    assert "sesudah" in output
    assert SECTION_BREAK_MARKER not in output
    assert "<w:sectPr>" in output


def test_missing_marker_is_left_untouched() -> None:
    output = render_front_matter("teks tanpa marker\n", load_format("undip-msi"))

    assert output.strip() == "teks tanpa marker"


def test_cover_markdown_is_not_rendered_from_metadata() -> None:
    output = _render(body='::: {custom-style="CoverTitle"}\nJUDUL MANUAL\n:::\n')

    assert "JUDUL MANUAL" in output
    assert _TITLE.upper() not in output
    assert "Nama Mahasiswa" not in output


def test_template_placeholders_are_not_expanded() -> None:
    output = _render(body="**Judul:** {{ title }}\n")

    assert "{{ title }}" in output


def test_page_break_raw_block_passes_through() -> None:
    output = _render()

    assert _PAGE_BREAK_XML in output


def test_heading_body_uppercase_and_line_break_for_roman() -> None:
    output = _render()

    assert f"# {LINE_BREAK}PENDAHULUAN" in output
    assert "## Latar Belakang" in output
    assert "### Detail" in output


def test_front_matter_headings_are_untouched() -> None:
    output = _render()

    assert "# LEMBAR PENGESAHAN {-}" in output
    assert "LEMBAR PENGESAHAN" not in output.replace("# LEMBAR PENGESAHAN {-}", "")


def test_appendix_stays_unnumbered() -> None:
    body = _BODY + "\n# Lampiran\n\n## Berkas\n\n- `document.md`\n"
    output = _render(body=body)

    assert "# Lampiran {-}" in output
    assert "## Berkas {-}" in output
    assert "LAMPIRAN" not in output


def test_arabic_dotted_assignment_has_no_line_break() -> None:
    output = _render(structure_id="assignment")

    assert "# PENDAHULUAN" in output
    assert f"# {LINE_BREAK}PENDAHULUAN" not in output


def _stage_context(
    tmp_path: Path,
    *,
    with_plantuml: bool = True,
    artifact_body: str = _BODY,
    document_body: str = _BODY,
) -> SimpleNamespace:
    structure = load_structure("thesis")
    format_ = load_format("undip-msi")
    document = _document(body=document_body)
    artifacts = ArtifactStore()
    if with_plantuml:
        source = tmp_path / "plantuml.md"
        source.write_text(artifact_body, encoding="utf-8", newline="\n")
        artifacts.put("plantuml.markdown", source)
    return SimpleNamespace(
        document=document,
        structure=structure,
        format=format_,
        workspace=Workspace(root=tmp_path / ".laporan-build", keep=True),
        artifacts=artifacts,
        dry_run=False,
    )


def test_stage_writes_markdown_idempotently(tmp_path: Path) -> None:
    stage = FrontMatterStage()
    ctx = _stage_context(tmp_path)

    first = stage.run(ctx)
    path = ctx.workspace.path("front_matter.md")
    assert first.changed is True
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert 'custom-style="CoverTitle"' in text
    assert SECTION_BREAK_MARKER not in text
    assert "<w:sectPr>" in text
    assert f"# {LINE_BREAK}PENDAHULUAN" in text
    assert ctx.artifacts.get("markdown") == path

    second = stage.run(ctx)
    assert second.changed is False
    assert path.read_text(encoding="utf-8") == text


def test_stage_reads_plantuml_artifact_not_document_body(tmp_path: Path) -> None:
    ctx = _stage_context(
        tmp_path,
        artifact_body="# Pendahuluan\n\nTeks dari artifact.\n",
        document_body="# Pendahuluan\n\nTeks dari body mentah.\n",
    )

    FrontMatterStage().run(ctx)

    text = ctx.workspace.path("front_matter.md").read_text(encoding="utf-8")
    assert "Teks dari artifact." in text
    assert "Teks dari body mentah." not in text


def test_stage_rejects_missing_plantuml_artifact(tmp_path: Path) -> None:
    ctx = _stage_context(tmp_path, with_plantuml=False)

    with pytest.raises(FrontMatterError) as excinfo:
        FrontMatterStage().run(ctx)

    assert excinfo.value.code == "FRONT-MATTER-INPUT"
    assert not ctx.workspace.path("front_matter.md").exists()


def test_stage_rejects_plantuml_artifact_pointing_to_missing_file(tmp_path: Path) -> None:
    ctx = _stage_context(tmp_path, with_plantuml=False)
    missing = tmp_path / "plantuml-hilang.md"
    ctx.artifacts.put("plantuml.markdown", missing)

    with pytest.raises(FrontMatterError) as excinfo:
        FrontMatterStage().run(ctx)

    assert excinfo.value.code == "FRONT-MATTER-INPUT"
    assert excinfo.value.path == missing
    assert str(missing) in str(excinfo.value)


def test_stage_rejects_plantuml_artifact_that_is_a_directory(tmp_path: Path) -> None:
    ctx = _stage_context(tmp_path, with_plantuml=False)
    directory = tmp_path / "plantuml-dir"
    directory.mkdir()
    ctx.artifacts.put("plantuml.markdown", directory)

    with pytest.raises(FrontMatterError) as excinfo:
        FrontMatterStage().run(ctx)

    assert excinfo.value.code == "FRONT-MATTER-INPUT"
    assert excinfo.value.path == directory


def test_stage_rejects_legacy_markdown_artifact_without_plantuml(tmp_path: Path) -> None:
    ctx = _stage_context(tmp_path, with_plantuml=False)
    legacy = tmp_path / "front_matter-lama.md"
    legacy.write_text(_BODY, encoding="utf-8", newline="\n")
    ctx.artifacts.put("markdown", legacy)

    with pytest.raises(FrontMatterError) as excinfo:
        FrontMatterStage().run(ctx)

    assert excinfo.value.code == "FRONT-MATTER-INPUT"


def test_document_without_plantuml_can_still_pass_front_matter(tmp_path: Path) -> None:
    ctx = _stage_context(tmp_path, with_plantuml=False)
    ctx.document = replace(
        ctx.document,
        body="# Pendahuluan\n\nTeks tanpa diagram.\n",
    )

    diag = PlantUmlStage().run(ctx)

    assert diag.status == "ok"
    assert diag.metrics["blocks"] == 0
    source = ctx.workspace.path("plantuml.md")
    assert ctx.artifacts.get("plantuml.markdown") == source
    assert source.read_text(encoding="utf-8") == ctx.document.body

    result = FrontMatterStage().run(ctx)

    assert result.status == "ok"
    front_matter = ctx.workspace.path("front_matter.md")
    text = front_matter.read_text(encoding="utf-8")
    assert f"# {LINE_BREAK}PENDAHULUAN" in text
    assert "Teks tanpa diagram." in text
    assert ctx.artifacts.get("markdown") == front_matter


def test_section_break_function_is_reusable() -> None:
    block = section_break(load_format("undip-msi"))

    assert block.startswith("```{=openxml}")
    assert "<w:sectPr>" in block
    assert block.endswith("```")

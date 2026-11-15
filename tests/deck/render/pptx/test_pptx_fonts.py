"""Tes tipografi Arial PPTX dan paket tanpa font tertanam."""

from xml.etree import ElementTree
from zipfile import ZipFile

from pptx import Presentation
from pptx.oxml.ns import qn

from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.pptx.shapes import primary_typeface
from autooffice.deck.render.protocol import OutputTarget, RenderRequest

_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _render_minimal(case, theme):
    return PptxRenderer().render(
        RenderRequest(
            deck=case.deck,
            layout=case.layout,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=case.workspace,
        )
    )


def _shape(presentation: Presentation, name: str):
    return next(shape for shape in presentation.slides[0].shapes if shape.name == name)


def _first_run(text_frame):
    return text_frame.paragraphs[0].runs[0]


def test_primary_typeface_resolves_arial_from_theme_stack() -> None:
    assert primary_typeface("Arial") == "Arial"
    assert primary_typeface("Arial, 'Helvetica Neue', sans-serif") == "Arial"


def test_theme_and_render_use_arial_without_embedded_fonts(minimal_case, theme) -> None:
    result = _render_minimal(minimal_case, theme)
    presentation = Presentation(str(result.artifact_path))

    assert theme.typography.family == "Arial"
    title_run = _first_run(_shape(presentation, "autooffice:key:s01.title.text").text_frame)
    body_run = _first_run(_shape(presentation, "autooffice:key:s01.body.item1.text").text_frame)
    table = _shape(presentation, "autooffice:table:s01.table1").table
    header_run = _first_run(table.cell(0, 0).text_frame)
    cell_run = _first_run(table.cell(1, 0).text_frame)
    notes_run = _first_run(presentation.slides[0].notes_slide.notes_text_frame)

    assert title_run.font.name == "Arial"
    assert title_run.font.bold is True
    assert body_run.font.name == "Arial"
    assert body_run.font.bold is False
    assert header_run.font.name == "Arial"
    assert header_run.font.bold is True
    assert cell_run.font.name == "Arial"
    assert cell_run.font.bold is False
    assert notes_run.font.name == "Arial"
    assert not any("font-embedding" in warning for warning in result.warnings)

    with ZipFile(result.artifact_path) as package:
        names = package.namelist()
        presentation_xml = ElementTree.fromstring(package.read("ppt/presentation.xml"))
        theme_xml = ElementTree.fromstring(package.read("ppt/theme/theme1.xml"))
        rels = ElementTree.fromstring(package.read("ppt/_rels/presentation.xml.rels"))

    assert not any(name.startswith("ppt/fonts/") for name in names)
    assert not any(name.lower().endswith(".fntdata") for name in names)
    assert presentation_xml.find(f".//{{{_P_NS}}}embeddedFontLst") is None
    latin = theme_xml.find(f".//{{{_A_NS}}}latin")
    assert latin is not None
    assert latin.get("typeface") == "Arial"
    assert all("relationships/font" not in relationship.get("Type", "") for relationship in rels)


def test_latin_typeface_is_arial_for_every_render_run(minimal_case, theme) -> None:
    result = _render_minimal(minimal_case, theme)
    presentation = Presentation(str(result.artifact_path))

    text_runs = [
        run
        for shape in presentation.slides[0].shapes
        if shape.has_text_frame
        for paragraph in shape.text_frame.paragraphs
        for run in paragraph.runs
    ]

    assert text_runs
    assert {run.font.name for run in text_runs} == {"Arial"}
    assert all(
        run.font._element.find(qn("a:latin")).get("typeface") == "Arial" for run in text_runs
    )

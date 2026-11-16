"""Tes tabel native, border token, fill, key sel, tinggi, dan alignment angka."""

import pytest
from _edge_helpers import new_slide
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn

from autooffice.deck.layout.measure import (
    measure_text,
    table_cell_padding_emu,
    table_column_widths,
)
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.pptx.shapes import Box, PptxRenderError
from autooffice.deck.render.pptx.table import render_table_block, table_cell_key
from autooffice.deck.render.protocol import OutputTarget, RenderRequest


def _render(case, theme):
    return PptxRenderer().render(
        RenderRequest(
            deck=case.deck,
            layout=case.layout,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=case.workspace,
        )
    )


def _table_shape(result):
    presentation = Presentation(str(result.artifact_path))
    return next(
        shape
        for shape in presentation.slides[0].shapes
        if shape.name == "autooffice:table:s01.table1"
    )


def test_table_is_native_and_header_is_first_row(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)
    shape = _table_shape(result)

    assert shape.shape_type == MSO_SHAPE_TYPE.TABLE
    assert shape.has_table is True
    assert shape.table.cell(0, 0).text == "Lane"
    assert shape.table.cell(1, 0).text == "Model"
    node = shape._element.find(".//" + qn("p:cNvPr"))
    assert node is not None
    assert node.get("title") == "s01.table1"
    assert node.get("descr") == "Lane, Deliverable, Status"


def test_every_table_cell_has_native_key_extension(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)
    table = _table_shape(result).table

    assert table_cell_key(table.cell(0, 2)) == "s01.table1.h3"
    assert table_cell_key(table.cell(2, 0)) == "s01.table1.r2.c1"
    assert table_cell_key(table.cell(2, 2)) == "s01.table1.r2.c3"


def test_table_header_uses_bold_and_body_uses_regular(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)
    table = _table_shape(result).table
    header_run = table.cell(0, 0).text_frame.paragraphs[0].runs[0]
    body_run = table.cell(1, 0).text_frame.paragraphs[0].runs[0]

    assert header_run.font.name == "Arial"
    assert header_run.font.bold is True
    assert body_run.font.name == "Arial"
    assert body_run.font.bold is False
    assert _latin_typeface(header_run) == "Arial"
    assert _latin_typeface(body_run) == "Arial"


def test_table_borders_and_fills_come_from_theme(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)
    table = _table_shape(result).table
    header = table.cell(0, 0)
    body = table.cell(1, 0)
    header_tc_pr = header._tc.get_or_add_tcPr()
    body_tc_pr = body._tc.get_or_add_tcPr()

    assert header.fill.fore_color.rgb == _rgb(theme.colors.accent)
    assert body.fill.fore_color.rgb == _rgb(theme.colors.surface)
    assert header_tc_pr.find(qn("a:lnT")) is not None
    assert header_tc_pr.find(qn("a:lnB")) is not None
    assert header_tc_pr.find(qn("a:lnL")) is None
    assert header_tc_pr.find(qn("a:lnR")) is None
    assert body_tc_pr.find(qn("a:lnB")) is not None
    assert body_tc_pr.find(qn("a:lnT")) is None
    assert body_tc_pr.find(qn("a:lnL")) is None
    assert body_tc_pr.find(qn("a:lnR")) is None


def test_numeric_cells_are_right_aligned(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)
    table = _table_shape(result).table

    numeric = table.cell(2, 2).text_frame.paragraphs[0]
    text = table.cell(1, 0).text_frame.paragraphs[0]

    assert numeric.alignment == PP_ALIGN.RIGHT
    assert text.alignment == PP_ALIGN.LEFT


def test_table_row_heights_follow_measured_content(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {
            "columns": ("Kolom A", "Kolom B"),
            "rows": (("panjang " * 25, "x"),),
        },
    )
    box = Box(left=0, top=0, width=4_000_000, height=4_500_000)

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")
    table = shapes[0].table
    padding = table_cell_padding_emu(theme)
    column_widths = table_column_widths(
        ("Kolom A", "Kolom B"),
        (("panjang " * 25, "x"),),
        table_width_emu=box.width,
        theme=theme,
    )
    cell_width = column_widths[0] - 2 * padding
    body_size_pt = max(theme.typography.body_pt, theme.typography.minimum_pt)
    tall_content = measure_text(
        "panjang " * 25,
        available_width_emu=cell_width,
        theme=theme,
        font_size_pt=body_size_pt,
        weight=theme.typography.weights[0],
    ).height_emu

    header_height = table.rows[0].height
    body_height = table.rows[1].height
    assert body_height != header_height
    assert body_height >= tall_content + 2 * padding
    assert shapes[0].top + sum(row.height for row in table.rows) <= box.bottom


def test_table_rejects_content_taller_than_box(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("A",), "rows": (("panjang " * 25,),)},
    )
    box = Box(left=0, top=0, width=2_000_000, height=800_000)

    with pytest.raises(PptxRenderError, match="melebihi kotak tabel"):
        render_table_block(new_slide(), block, box, theme, slide_id="s01")


def test_table_fits_exact_box(theme) -> None:
    columns = ("A", "B")
    rows = (("1", "2"), ("3", "4"))
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {
            "columns": columns,
            "rows": rows,
        },
    )
    width = 4_000_000
    padding = table_cell_padding_emu(theme)
    column_widths = table_column_widths(
        columns,
        rows,
        table_width_emu=width,
        theme=theme,
    )
    cell_widths = [column_width - 2 * padding for column_width in column_widths]
    body_size_pt = max(theme.typography.body_pt, theme.typography.minimum_pt)

    def row_content(values: tuple[str, ...], weight: int) -> int:
        return max(
            measure_text(
                value,
                available_width_emu=cell_widths[index],
                theme=theme,
                font_size_pt=body_size_pt,
                weight=weight,
            ).height_emu
            for index, value in enumerate(values)
        )

    margin = 2 * padding
    table_height = (
        row_content(columns, theme.typography.weights[1])
        + margin
        + row_content(rows[0], theme.typography.weights[0])
        + margin
        + row_content(rows[1], theme.typography.weights[0])
        + margin
    )
    box = Box(
        left=0,
        top=0,
        width=width,
        height=table_height,
    )

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")

    assert len(shapes) == 1
    frame = shapes[0]
    assert frame.top == box.top
    assert sum(row.height for row in frame.table.rows) == table_height
    assert frame.top + frame.height == box.top + table_height


@pytest.mark.parametrize(
    "value",
    ["1.2.3", "1,2,3", "1,234,56", "1.234.56", "1,234,567,89", "nan", "inf", "", "12px"],
)
def test_malformed_numbers_align_left(theme, value: str) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("Value",), "rows": ((value,),)},
    )
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")

    assert shapes[0].table.cell(1, 0).text_frame.paragraphs[0].alignment == PP_ALIGN.LEFT


@pytest.mark.parametrize(
    "value",
    ["42", "-3.5", "1,234.56", "72%", "+0.5", "1234", "1,234", "1.234,56", "12%"],
)
def test_strict_numeric_values_align_right(theme, value: str) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("Value",), "rows": ((value,),)},
    )
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")

    assert shapes[0].table.cell(1, 0).text_frame.paragraphs[0].alignment == PP_ALIGN.RIGHT


def test_emphasis_column_measures_emphasized_header_and_body(theme) -> None:
    header = "review eksperimen delta tambahan hasil"
    body = "arsitektur column arsitektur kontrak measurement arsitektur"
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {
            "columns": ("A", header),
            "rows": (("1", body), ("2", body)),
            "emphasis_column": 2,
        },
    )
    padding = table_cell_padding_emu(theme)
    width = 4_000_000
    column_widths = table_column_widths(
        ("A", header),
        (("1", body), ("2", body)),
        table_width_emu=width,
        theme=theme,
        emphasis_column=2,
    )
    cell_width = column_widths[1] - 2 * padding
    font_size_pt = max(theme.typography.body_pt, theme.typography.minimum_pt)

    def measure(text: str, weight: int):
        return measure_text(
            text,
            available_width_emu=cell_width,
            theme=theme,
            font_size_pt=font_size_pt,
            weight=weight,
        )

    header_emphasis = measure(header, theme.typography.weights[2])
    body_emphasis = measure(body, theme.typography.weights[1])
    assert header_emphasis.width_emu >= measure(header, theme.typography.weights[1]).width_emu
    assert body_emphasis.width_emu >= measure(body, theme.typography.weights[0]).width_emu

    table_height = header_emphasis.height_emu + 2 * padding
    table_height += 2 * (body_emphasis.height_emu + 2 * padding)
    box = Box(
        left=0,
        top=0,
        width=width,
        height=table_height,
    )

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")
    frame = shapes[0]
    rows = frame.table.rows

    assert rows[0].height >= header_emphasis.height_emu + 2 * padding
    assert rows[1].height >= body_emphasis.height_emu + 2 * padding
    assert rows[2].height >= body_emphasis.height_emu + 2 * padding
    assert sum(row.height for row in rows) == table_height


def test_emphasis_column_changes_fill_and_weight(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {
            "columns": ("A", "B", "C"),
            "rows": (("1", "2", "3"),),
            "emphasis_column": 2,
        },
    )
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")
    table = shapes[0].table
    header = table.cell(0, 1)
    body = table.cell(1, 1)
    plain_header = table.cell(0, 0)
    plain_body = table.cell(1, 0)

    assert header.fill.fore_color.rgb == _rgb(theme.colors.accent_deep)
    assert plain_header.fill.fore_color.rgb == _rgb(theme.colors.accent)
    assert body.fill.fore_color.rgb == _rgb(theme.colors.accent_soft)
    assert plain_body.fill.fore_color.rgb == _rgb(theme.colors.surface)
    emphasis_run = body.text_frame.paragraphs[0].runs[0]
    plain_run = plain_body.text_frame.paragraphs[0].runs[0]
    assert emphasis_run.font.name == "Arial"
    assert emphasis_run.font.bold is True
    assert plain_run.font.name == "Arial"
    assert plain_run.font.bold is False


def test_table_columns_are_content_aware_with_min_and_max(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {
            "columns": ("ID", "Nama", "Keterangan", "Nilai"),
            "rows": (("1", "A", "deskripsi panjang " * 3, "10"),),
        },
    )
    box = Box(left=0, top=0, width=4_000_000, height=8_000_000)

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")
    widths = [column.width for column in shapes[0].table.columns]
    minimum = 40 * 9525
    maximum = round(box.width * 0.4)

    assert sum(widths) == box.width
    assert widths[2] > widths[0]
    assert widths[0] >= minimum
    assert max(widths) <= maximum


def test_numeric_header_alignment_matches_numeric_body(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("Nama", "Nilai"), "rows": (("A", "1"), ("B", "2"))},
    )
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")
    table = shapes[0].table

    assert table.cell(0, 0).text_frame.paragraphs[0].alignment == PP_ALIGN.LEFT
    assert table.cell(0, 1).text_frame.paragraphs[0].alignment == PP_ALIGN.RIGHT
    assert table.cell(1, 1).text_frame.paragraphs[0].alignment == PP_ALIGN.RIGHT


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("007", PP_ALIGN.LEFT),
        ("0012", PP_ALIGN.LEFT),
        ("0", PP_ALIGN.RIGHT),
    ],
)
def test_leading_zero_identifiers_align_as_text(theme, value: str, expected: PP_ALIGN) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("ID",), "rows": ((value,),)},
    )
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")

    assert shapes[0].table.cell(1, 0).text_frame.paragraphs[0].alignment == expected


def test_table_cell_padding_uses_md_token(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("A",), "rows": (("1",),)},
    )
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")
    cell = shapes[0].table.cell(0, 0)
    padding = theme.spacing.md_emu

    assert cell.margin_left == padding
    assert cell.margin_right == padding
    assert cell.margin_top == padding
    assert cell.margin_bottom == padding


def _latin_typeface(run) -> str:
    latin = run.font._element.find(qn("a:latin"))
    assert latin is not None
    return latin.get("typeface", "")


def _rgb(color: str) -> object:
    from pptx.dml.color import RGBColor

    return RGBColor.from_string(color[1:])

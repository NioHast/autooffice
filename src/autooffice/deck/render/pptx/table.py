"""Tabel native PPTX dengan border, fill, dan key sel dari token."""

import re
from collections.abc import Mapping

from lxml import etree
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.shapes.base import BaseShape
from pptx.shapes.graphfrm import GraphicFrame
from pptx.slide import Slide
from pptx.table import _Cell
from pptx.util import Emu

from autooffice.deck.layout.measure import (
    measure_text,
    table_cell_padding_emu,
    table_column_widths,
)
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.design.theme import Theme

from .shapes import (
    KEY_EXTENSION_TAG,
    TABLE_MARKER,
    Box,
    PptxRenderError,
    add_extension_keys,
    apply_paragraph_style,
    apply_run_style,
    field_rows,
    field_sequence,
    record_render_warning,
    rgb,
    set_namespace_marker,
)
from .textbox import TextStyle

# Angka ketat: tanda opsional, kelompok ribuan tiga digit dengan pemisah yang
# konsisten, desimal opsional memakai pemisah berbeda dari ribuan, persen
# opsional. String seperti "1.2.3", "1,2,3", "1,234,56", "nan", dan "inf"
# ditolak; pemisah ribuan tidak boleh dipakai ulang sebagai pemisah desimal.
_NUMERIC_PATTERN = re.compile(
    r"^[+-]?(?:"
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"
    r"|\d{1,3}(?:\.\d{3})+(?:,\d+)?"
    r"|\d+(?:[.,]\d+)?"
    r"|[.,]\d+"
    r")%?$"
)


def table_cell_key(cell: _Cell) -> str | None:
    """Baca key satu sel tabel dari ``a:tcPr/a:extLst`` native."""
    tc_pr = cell._tc.tcPr
    if tc_pr is None:
        return None
    keys = tuple(element.text for element in tc_pr.iter(KEY_EXTENSION_TAG) if element.text)
    return keys[0] if keys else None


def set_table_cell_key(cell: _Cell, key: str) -> None:
    """Simpan key sel di extension ``a:tcPr`` tanpa mengganti tabel native."""
    if not key:
        raise PptxRenderError("Key sel tabel tidak boleh kosong.")
    add_extension_keys(cell._tc.get_or_add_tcPr(), (key,))


def render_table_block(
    slide: Slide,
    block: BlockIR,
    box: Box,
    theme: Theme,
    *,
    slide_id: str,
) -> tuple[BaseShape, ...]:
    """Render block table sebagai ``shapes.add_table`` native."""
    columns = field_sequence(block.fields, "columns", block_id=block.block_id)
    rows = field_rows(block.fields, "rows", block_id=block.block_id)
    if not columns:
        raise PptxRenderError(f"Block table '{block.block_id}' tidak memiliki kolom.")
    if not rows:
        raise PptxRenderError(f"Block table '{block.block_id}' tidak memiliki baris.")
    width_mismatch = [index for index, row in enumerate(rows, start=1) if len(row) != len(columns)]
    if width_mismatch:
        row_index = width_mismatch[0]
        raise PptxRenderError(
            f"Block table '{block.block_id}' baris {row_index} memiliki "
            f"{len(rows[row_index - 1])} sel; jumlah kolom adalah {len(columns)}."
        )

    namespace = f"{slide_id}.{block.block_id}"
    typography = theme.typography
    header_style = TextStyle(
        size_pt=max(typography.body_pt, typography.minimum_pt),
        weight=typography.weights[1],
        color=theme.colors.accent_ink,
        family=typography.family,
        line_height=typography.line_height,
        tracking_em=typography.tracking_em,
    )
    body_text_style = TextStyle(
        size_pt=max(typography.body_pt, typography.minimum_pt),
        weight=typography.weights[0],
        color=theme.colors.ink,
        family=typography.family,
        line_height=typography.line_height,
        tracking_em=typography.tracking_em,
    )
    table_box = box
    emphasis = _emphasis_column(block.fields, column_count=len(columns))
    header_emphasis_style = TextStyle(
        size_pt=header_style.size_pt,
        weight=typography.weights[2],
        color=header_style.color,
        family=header_style.family,
        line_height=header_style.line_height,
        tracking_em=header_style.tracking_em,
    )
    body_emphasis_style = TextStyle(
        size_pt=body_text_style.size_pt,
        weight=typography.weights[1],
        color=body_text_style.color,
        family=body_text_style.family,
        line_height=body_text_style.line_height,
        tracking_em=body_text_style.tracking_em,
    )
    column_widths = table_column_widths(
        columns,
        rows,
        table_width_emu=table_box.width,
        theme=theme,
        emphasis_column=emphasis,
    )
    row_content_heights = _measure_row_content_heights(
        columns,
        rows,
        column_widths=column_widths,
        theme=theme,
        header_style=header_style,
        body_style=body_text_style,
        emphasis_column=emphasis,
        header_emphasis_style=header_emphasis_style,
        body_emphasis_style=body_emphasis_style,
    )
    row_heights = _allocate_row_heights(
        row_content_heights,
        margin_emu=2 * table_cell_padding_emu(theme),
        available_height_emu=table_box.height,
        block_id=block.block_id,
    )
    frame = slide.shapes.add_table(
        rows=len(rows) + 1,
        cols=len(columns),
        left=Emu(table_box.left),
        top=Emu(table_box.top),
        width=Emu(table_box.width),
        height=Emu(table_box.height),
    )
    table = frame.table
    table.first_row = True
    table.horz_banding = False
    table.first_col = False
    table.last_row = False
    table.last_col = False
    _remove_table_style(frame)
    _distribute_columns(frame, column_widths)
    _distribute_rows(frame, row_heights)
    alt = ", ".join(columns)
    set_namespace_marker(frame, TABLE_MARKER, namespace, description=alt)
    numeric_columns = _numeric_columns(rows, column_count=len(columns))

    for column_index, header in enumerate(columns, start=1):
        cell = table.cell(0, column_index - 1)
        emphasized = emphasis == column_index
        _style_cell(
            cell,
            header,
            style=header_emphasis_style if emphasized else header_style,
            theme=theme,
            fill=theme.colors.accent_deep if emphasized else theme.colors.accent,
            numeric=numeric_columns[column_index - 1],
            header=True,
            key=f"{namespace}.h{column_index}",
        )
    for row_index, row in enumerate(rows, start=1):
        fill = theme.colors.surface if row_index % 2 == 1 else theme.colors.surface_alt
        for column_index, value in enumerate(row, start=1):
            cell = table.cell(row_index, column_index - 1)
            emphasized = emphasis == column_index
            _style_cell(
                cell,
                value,
                style=body_emphasis_style if emphasized else body_text_style,
                theme=theme,
                fill=theme.colors.accent_soft if emphasized else fill,
                numeric=_looks_numeric(value),
                header=False,
                key=f"{namespace}.r{row_index}.c{column_index}",
            )
    return (frame,)


def _remove_table_style(frame: GraphicFrame) -> None:
    tbl_pr = frame._element.find(".//" + qn("a:tblPr"))
    if tbl_pr is None:
        return
    style_id = tbl_pr.find(qn("a:tableStyleId"))
    if style_id is not None:
        tbl_pr.remove(style_id)


def _distribute_columns(frame: GraphicFrame, widths_emu: tuple[int, ...]) -> None:
    table = frame.table
    if len(widths_emu) != len(table.columns):
        raise PptxRenderError(
            f"Jumlah lebar kolom {len(widths_emu)} tidak cocok dengan tabel "
            f"{len(table.columns)} kolom."
        )
    for index, width in enumerate(widths_emu):
        if width <= 0:
            raise PptxRenderError(f"Lebar kolom tabel ke-{index + 1} harus positif.")
        table.columns[index].width = Emu(width)


def _distribute_rows(frame: GraphicFrame, row_heights: tuple[int, ...]) -> None:
    table = frame.table
    if len(row_heights) != len(table.rows):
        raise PptxRenderError(
            f"Jumlah tinggi baris {len(row_heights)} tidak cocok dengan tabel "
            f"{len(table.rows)} baris."
        )
    for index, height in enumerate(row_heights):
        if height <= 0:
            raise PptxRenderError(f"Tinggi baris tabel ke-{index + 1} harus positif.")
        table.rows[index].height = Emu(height)


def _measure_row_content_heights(
    columns: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
    *,
    column_widths: tuple[int, ...],
    theme: Theme,
    header_style: TextStyle,
    body_style: TextStyle,
    emphasis_column: int | None,
    header_emphasis_style: TextStyle,
    body_emphasis_style: TextStyle,
) -> tuple[int, ...]:
    """Ukur tinggi konten setiap baris dengan lebar kolom nyata saat render."""
    padding = table_cell_padding_emu(theme)
    cell_widths = tuple(max(1, width - 2 * padding) for width in column_widths)

    def measure(
        row: tuple[str, ...],
        style: TextStyle,
        emphasis_style: TextStyle,
    ) -> int:
        return max(
            measure_text(
                cell,
                available_width_emu=cell_widths[column_index - 1],
                theme=theme,
                font_size_pt=(
                    emphasis_style.size_pt if emphasis_column == column_index else style.size_pt
                ),
                weight=(emphasis_style.weight if emphasis_column == column_index else style.weight),
                tracking_em=(
                    emphasis_style.tracking_em
                    if emphasis_column == column_index
                    else style.tracking_em
                ),
            ).height_emu
            for column_index, cell in enumerate(row, start=1)
        )

    content_heights = [
        measure(columns, header_style, header_emphasis_style),
    ]
    content_heights.extend(measure(row, body_style, body_emphasis_style) for row in rows)
    return tuple(content_heights)


def _allocate_row_heights(
    content_heights: tuple[int, ...],
    *,
    margin_emu: int,
    available_height_emu: int,
    block_id: str,
) -> tuple[int, ...]:
    """Bagi tinggi tabel proporsional terhadap konten, dengan margin minimum."""
    if margin_emu < 0:
        raise PptxRenderError("Margin vertikal sel tabel tidak boleh negatif.")
    minimums = [height + margin_emu for height in content_heights]
    total_minimum = sum(minimums)
    if total_minimum > available_height_emu:
        raise PptxRenderError(
            f"Block table '{block_id}' memerlukan tinggi minimum {total_minimum} EMU, "
            f"melebihi kotak tabel {available_height_emu} EMU."
        )
    extra = available_height_emu - total_minimum
    if extra == 0:
        return tuple(minimums)
    total_content = sum(content_heights)
    allocated = [
        minimum + extra * content // total_content
        for minimum, content in zip(minimums, content_heights, strict=True)
    ]
    remainder = available_height_emu - sum(allocated)
    largest = max(range(len(content_heights)), key=lambda index: content_heights[index])
    allocated[largest] += remainder
    return tuple(allocated)


def _emphasis_column(fields: Mapping[str, object], *, column_count: int) -> int | None:
    """Baca kolom emphasis 1-based bila valid untuk jumlah kolom tabel."""
    value = fields.get("emphasis_column")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if 1 <= value <= column_count:
        return value
    return None


def _style_cell(
    cell: _Cell,
    text: str,
    *,
    style: TextStyle,
    theme: Theme,
    fill: str,
    numeric: bool,
    header: bool,
    key: str,
) -> None:
    text_frame = cell.text_frame
    text_frame.word_wrap = True
    text_frame.auto_size = MSO_AUTO_SIZE.NONE
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    padding = table_cell_padding_emu(theme)
    cell.margin_left = Emu(padding)
    cell.margin_right = Emu(padding)
    cell.margin_top = Emu(padding)
    cell.margin_bottom = Emu(padding)
    paragraph = text_frame.paragraphs[0]
    paragraph.text = text
    apply_paragraph_style(
        paragraph,
        line_height=style.line_height,
        font_size_pt=style.size_pt,
        alignment=PP_ALIGN.RIGHT if numeric else PP_ALIGN.LEFT,
    )
    for run in paragraph.runs:
        warning = apply_run_style(
            run,
            family=style.family,
            size_pt=style.size_pt,
            weight=style.weight,
            color=style.color,
            tracking_em=style.tracking_em,
        )
        if warning is not None:
            record_render_warning(warning)
    cell.fill.solid()  # type: ignore[no-untyped-call]
    cell.fill.fore_color.rgb = rgb(fill)
    _set_cell_borders(cell._tc.get_or_add_tcPr(), theme, header=header)
    set_table_cell_key(cell, key)


def _numeric_columns(
    rows: tuple[tuple[str, ...], ...],
    *,
    column_count: int,
) -> tuple[bool, ...]:
    """Tandai kolom yang seluruh sel body non-kosongnya angka."""
    result: list[bool] = []
    for column_index in range(column_count):
        values = [
            row[column_index]
            for row in rows
            if column_index < len(row) and row[column_index].strip()
        ]
        result.append(bool(values) and all(_looks_numeric(value) for value in values))
    return tuple(result)


def _set_cell_borders(tc_pr: etree._Element, theme: Theme, *, header: bool) -> None:
    """Hapus grid internal dan sisakan garis horizontal yang terbaca."""
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        existing = tc_pr.find(qn(tag))
        if existing is not None:
            tc_pr.remove(existing)
    color = theme.colors.accent_deep if header else theme.colors.border
    tc_pr.insert(0, _border_line("lnB", theme, color=color))
    if header:
        tc_pr.insert(0, _border_line("lnT", theme, color=color))


def _border_line(side: str, theme: Theme, *, color: str) -> etree._Element:
    line = OxmlElement(f"a:{side}")
    line.set("w", str(theme.spacing.divider_emu))
    line.set("cap", "flat")
    line.set("cmpd", "sng")
    line.set("algn", "ctr")
    fill = OxmlElement("a:solidFill")
    color_element = OxmlElement("a:srgbClr")
    color_element.set("val", color[1:].upper())
    fill.append(color_element)
    line.append(fill)
    dash = OxmlElement("a:prstDash")
    dash.set("val", "solid")
    line.append(dash)
    return line


def _looks_numeric(text: str) -> bool:
    """Angka ketat; ID berawalan nol diperlakukan sebagai teks."""
    stripped = text.strip()
    if not stripped:
        return False
    unsigned = stripped.lstrip("+-")
    if unsigned.isdigit() and len(unsigned) > 1 and unsigned.startswith("0"):
        return False
    return _NUMERIC_PATTERN.fullmatch(stripped) is not None

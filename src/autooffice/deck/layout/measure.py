"""Pengukuran teks dan block memakai metrik font yang dibundel.

Pengukuran deterministik dan offline. Tidak ada browser, COM, autofit, shrink,
atau ellipsis. Line-height, tracking, padding, dan ukuran font berasal dari
``Theme``; ukuran font yang dipakai adalah ukuran asli, bukan ukuran turunan.

Ukuran dan bobot role disalin dari renderer PPTX supaya layout dan render
memakai kontrak tipografi yang sama. Teks diukur dengan metrik Liberation Sans
yang kompatibel dengan Arial; code diukur dengan advance monospace konservatif
karena family code bukan Arial.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import cast

from PIL import ImageFont

from autooffice.deck.layout.spec import LayoutError
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.design.fonts import font_path
from autooffice.design.theme import Theme

_EMU_PER_POINT = 12700
_EMU_PER_PIXEL = 9525
_FONT_PIXEL_SIZE = 128
# Batas atas cache pengukuran; teks yang sama sering diukur berulang antar
# slide, tetapi jumlah entri tetap dibatasi supaya deck besar tidak menahan
# memori tanpa batas.
_MEASURE_CACHE_MAXSIZE = 8192
# Lebar minimum kolom tabel 40 px dan maksimum 40% lebar tabel. Nilai px
# dikonversi ke EMU agar pengukuran dan renderer memakai satuan yang sama.
_TABLE_COLUMN_MIN_EMU = 40 * _EMU_PER_PIXEL
_TABLE_COLUMN_MAX_FRACTION = 0.4
# Lebar pengukuran alami kolom: cukup besar agar teks tidak terbungkus lebih
# dulu sebelum lebar alaminya dibandingkan dengan batas 40%.
_TABLE_NATURAL_WIDTH_EMU = 100_000_000

_ROLE_NAMES = frozenset({"display", "title", "lead", "body", "caption", "label", "kicker"})
_FONT_BY_WEIGHT: tuple[tuple[int, str], ...] = (
    (400, "LiberationSans-Regular.ttf"),
    (700, "LiberationSans-Bold.ttf"),
)

# Cascadia Mono/Consolas berada di sekitar 0.55-0.60 em. Nilai konservatif ini
# sengaja dilebihkan supaya code yang mendekati lebar slot tidak lolos.
_CODE_ADVANCE_EM = 0.62
_CODE_TAB_WIDTH = 4

# Kontrak gutter nomor baris dengan renderer PPTX:
# ``autooffice.deck.render.pptx.textbox.render_code_block`` mengukur teks nomor
# terlebar memakai ``measure_code_text`` lalu menambahkan
# ``theme.spacing.sm_emu`` sebagai jarak. Layout memakai fungsi
# ``line_number_gutter_width`` dan ``code_text_width`` di bawah sebagai sumber
# tunggal; salinan renderer harus tetap identik (dijaga test paritas).


class MeasurementError(LayoutError):
    """Parameter pengukuran tidak valid."""


@dataclass(frozen=True, slots=True)
class TextMeasurement:
    """Hasil pengukuran satu blok teks."""

    width_emu: int
    height_emu: int
    line_count: int
    overflow_width_emu: int


@dataclass(frozen=True, slots=True)
class RoleTypography:
    """Ukuran, bobot, dan tracking satu role teks dari token theme."""

    size_pt: float
    weight: int
    tracking_em: float


@dataclass(frozen=True, slots=True)
class BlockMeasurement:
    """Tinggi satu block beserta temuan overflow horizontal dan vertikal."""

    width_emu: int
    height_emu: int
    line_count: int
    overflow_width_emu: int
    overflow_height_emu: int = 0
    overflow_width_leaf: str | None = None
    overflow_height_leaf: str | None = None
    height_leaf: str | None = None


@dataclass(frozen=True, slots=True)
class _TextPart:
    """Satu bagian teks block beserta leaf key-nya."""

    leaf: str
    measurement: TextMeasurement


def measure_text(
    text: str,
    *,
    available_width_emu: int,
    theme: Theme,
    font_size_pt: float | None = None,
    weight: int = 400,
    line_height: float | None = None,
    tracking_em: float | None = None,
) -> TextMeasurement:
    """Ukur teks dengan word wrapping pada lebar yang tersedia.

    Teks yang tidak muat tetap dilaporkan melalui ``overflow_width_emu``;
    fungsi ini tidak memotong, mengecilkan font, atau menambahkan ellipsis.
    Hasil di-memoize berdasarkan ukuran font, line-height, dan tracking yang
    sudah diresolusi, sehingga ``Theme`` tetap menjadi satu-satunya sumber
    nilai tipografi tanpa ikut disimpan di cache.
    """
    if available_width_emu <= 0:
        raise MeasurementError("Lebar pengukuran teks harus positif.")
    size_pt = theme.typography.body_pt if font_size_pt is None else font_size_pt
    if size_pt <= 0:
        raise MeasurementError("Ukuran font pengukuran harus positif.")
    effective_line_height = theme.typography.line_height if line_height is None else line_height
    if effective_line_height <= 0:
        raise MeasurementError("Line-height pengukuran harus positif.")
    effective_tracking = theme.typography.tracking_em if tracking_em is None else tracking_em

    return _measure_text_cached(
        text,
        available_width_emu,
        size_pt,
        weight,
        effective_line_height,
        effective_tracking,
    )


@lru_cache(maxsize=_MEASURE_CACHE_MAXSIZE)
def _measure_text_cached(
    text: str,
    available_width_emu: int,
    font_size_pt: float,
    weight: int,
    line_height: float,
    tracking_em: float,
) -> TextMeasurement:
    font = _load_font(_font_file_for_weight(weight))
    font_size_emu = _round_emu(font_size_pt * _EMU_PER_POINT)
    line_height_emu = max(1, _round_emu(font_size_emu * line_height))
    scale = font_size_emu / _FONT_PIXEL_SIZE
    tracking_emu = tracking_em * font_size_emu

    lines, overflow_width_emu = _wrap_text(
        text,
        width_emu=available_width_emu,
        font=font,
        scale=scale,
        tracking_emu=tracking_emu,
    )
    widths = tuple(
        _line_width_emu(line, font=font, scale=scale, tracking_emu=tracking_emu) for line in lines
    )
    content_width = max(widths, default=0)
    return TextMeasurement(
        width_emu=content_width,
        height_emu=len(lines) * line_height_emu,
        line_count=len(lines),
        overflow_width_emu=max(overflow_width_emu, content_width - available_width_emu),
    )


def measure_code_text(
    text: str,
    *,
    available_width_emu: int,
    theme: Theme,
    font_size_pt: float | None = None,
    line_height: float | None = None,
) -> TextMeasurement:
    """Ukur code dengan advance monospace dan preservasi spasi.

    Setiap baris eksplisit dipecah per karakter bila melebihi kapasitas slot.
    Spasi di awal dan spasi ganda ikut dihitung; tab diperluas ke tab stop
    empat kolom. Tidak ada glyph monospace yang dibundel, jadi advance diambil
    konservatif dari ukuran font. Hasil di-memoize berdasarkan ukuran font dan
    line-height yang sudah diresolusi; fungsi ini murni terhadap argumen
    eksplisit dan konstanta modul.
    """
    if available_width_emu <= 0:
        raise MeasurementError("Lebar pengukuran teks harus positif.")
    size_pt = theme.code.size_pt if font_size_pt is None else font_size_pt
    size_pt = max(size_pt, theme.typography.minimum_pt)
    if size_pt <= 0:
        raise MeasurementError("Ukuran font pengukuran harus positif.")
    effective_line_height = theme.code.line_height if line_height is None else line_height
    if effective_line_height <= 0:
        raise MeasurementError("Line-height pengukuran harus positif.")

    return _measure_code_text_cached(
        text,
        available_width_emu,
        size_pt,
        effective_line_height,
    )


@lru_cache(maxsize=_MEASURE_CACHE_MAXSIZE)
def _measure_code_text_cached(
    text: str,
    available_width_emu: int,
    font_size_pt: float,
    line_height: float,
) -> TextMeasurement:
    font_size_emu = font_size_pt * _EMU_PER_POINT
    line_height_emu = max(1, _round_emu(font_size_emu * line_height))
    character_width_emu = font_size_emu * _CODE_ADVANCE_EM
    capacity = max(1, int(available_width_emu // character_width_emu))

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    line_count = 0
    max_width_emu = 0
    for raw_line in normalized.split("\n"):
        line = raw_line.expandtabs(_CODE_TAB_WIDTH)
        chunks = _code_chunks(line, capacity)
        line_count += len(chunks)
        for chunk in chunks:
            width = _round_emu(len(chunk) * character_width_emu)
            max_width_emu = max(max_width_emu, width)
    return TextMeasurement(
        width_emu=max_width_emu,
        height_emu=max(1, line_count) * line_height_emu,
        line_count=max(1, line_count),
        overflow_width_emu=max(0, max_width_emu - available_width_emu),
    )


def code_line_count(code: str) -> int:
    """Hitung baris logis code; baris kosong tetap mendapat nomor.

    Nilai ini sama dengan jumlah nomor baris yang digambar renderer PPTX.
    """
    normalized = code.replace("\r\n", "\n").replace("\r", "\n")
    return max(1, len(normalized.split("\n")))


def line_number_gutter_width(
    line_count: int,
    *,
    theme: Theme,
    available_width_emu: int,
) -> int:
    """Lebar gutter nomor baris dari teks nomor terlebar.

    Kontrak dengan renderer PPTX: gutter memakai advance monospace yang sama
    dengan :func:`measure_code_text`, dan lebarnya adalah hasil pengukuran
    string nomor terlebar, bukan konstanta tetap. Renderer menambahkan
    ``theme.spacing.sm_emu`` sebagai jarak setelah gutter.
    """
    widest = str(max(1, line_count))
    measurement = measure_code_text(
        widest,
        available_width_emu=max(1, available_width_emu),
        theme=theme,
    )
    return max(1, measurement.width_emu)


def code_text_width(
    code: str,
    *,
    inner_width_emu: int,
    theme: Theme,
    line_numbers: bool,
) -> int:
    """Lebar teks code setelah gutter nomor baris dan jarak gutter.

    ``inner_width_emu`` adalah lebar slot setelah padding kartu. Bila nomor
    baris aktif, lebar dikurangi gutter dan ``theme.spacing.sm_emu`` persis
    seperti kotak code pada renderer PPTX. Default renderer untuk
    ``line_numbers`` adalah ``True``.
    """
    if not line_numbers:
        return max(1, inner_width_emu)
    gutter_width = line_number_gutter_width(
        code_line_count(code),
        theme=theme,
        available_width_emu=inner_width_emu,
    )
    return max(1, inner_width_emu - gutter_width - theme.spacing.sm_emu)


def measure_block(
    block: BlockIR,
    *,
    width_emu: int,
    theme: Theme,
    max_height_emu: int | None = None,
) -> BlockMeasurement:
    """Ukur tinggi satu block pada lebar slot yang diberikan.

    ``max_height_emu`` hanya dipakai media (``image``, ``chart``, ``diagram``):
    media memakai mode contain dan tinggi yang tersedia, bukan tinggi natural
    tetap. Block non-media mengabaikan batas ini dan tetap dilaporkan lewat
    overflow bila tidak muat.
    """
    if width_emu <= 0:
        raise MeasurementError(f"Lebar slot block '{block.block_id}' harus positif.")
    block_type = block.block_type
    if block_type == "text":
        return _measure_text_block(block, width_emu=width_emu, theme=theme)
    if block_type == "bullets":
        return _measure_bullets_block(block, width_emu=width_emu, theme=theme)
    if block_type == "quote":
        return _measure_quote_block(block, width_emu=width_emu, theme=theme)
    if block_type == "metric":
        return _measure_metric_block(block, width_emu=width_emu, theme=theme)
    if block_type == "code":
        return _measure_code_block(block, width_emu=width_emu, theme=theme)
    if block_type == "table":
        return _measure_table_block(block, width_emu=width_emu, theme=theme)
    if block_type in {"image", "diagram", "chart"}:
        return _measure_media_block(
            block,
            width_emu=width_emu,
            theme=theme,
            max_height_emu=max_height_emu,
        )
    if block_type == "divider":
        return BlockMeasurement(
            width_emu=width_emu,
            height_emu=theme.spacing.divider_emu,
            line_count=0,
            overflow_width_emu=0,
        )
    if block_type == "spacer":
        size = _as_text(block.fields.get("size")) or "md"
        height = {
            "sm": theme.spacing.sm_emu,
            "md": theme.spacing.md_emu,
            "lg": theme.spacing.lg_emu,
        }.get(size, theme.spacing.md_emu)
        return BlockMeasurement(
            width_emu=width_emu,
            height_emu=height,
            line_count=0,
            overflow_width_emu=0,
        )
    body = body_typography(theme)
    parts = [
        _TextPart(
            "label",
            measure_text(
                _as_text(block.fields.get("text"))
                or _as_text(block.fields.get("label"))
                or _as_text(block.fields.get("value")),
                available_width_emu=_inner_width(width_emu),
                theme=theme,
                font_size_pt=body.size_pt,
                weight=body.weight,
                tracking_em=body.tracking_em,
            ),
        )
    ]
    return _measure_parts(parts, theme=theme)


def minimum_block_height(
    block: BlockIR,
    *,
    width_emu: int,
    theme: Theme,
) -> int:
    """Tinggi minimum block untuk reservasi row berikutnya.

    Untuk media, batas tinggi nol memilih tinggi minimum contain, bukan tinggi
    natural 16:9. Teks dan tabel tetap memakai tinggi naturalnya karena tidak
    boleh di-shrink.
    """
    return measure_block(block, width_emu=width_emu, theme=theme, max_height_emu=0).height_emu


def _measure_text_block(block: BlockIR, *, width_emu: int, theme: Theme) -> BlockMeasurement:
    inner = _inner_width(width_emu)
    parts: list[_TextPart] = []
    heading = _as_text(block.fields.get("heading"))
    if heading:
        heading_style = body_typography(theme, weight=theme.typography.weights[1])
        parts.append(
            _TextPart(
                "heading",
                measure_text(
                    heading,
                    available_width_emu=inner,
                    theme=theme,
                    font_size_pt=heading_style.size_pt,
                    weight=heading_style.weight,
                    tracking_em=heading_style.tracking_em,
                ),
            )
        )
    role_style = role_typography(theme, block.role)
    parts.append(
        _TextPart(
            "text",
            measure_text(
                _as_text(block.fields.get("text")),
                available_width_emu=inner,
                theme=theme,
                font_size_pt=role_style.size_pt,
                weight=role_style.weight,
                tracking_em=role_style.tracking_em,
            ),
        )
    )
    return _measure_parts(parts, theme=theme)


def _measure_bullets_block(block: BlockIR, *, width_emu: int, theme: Theme) -> BlockMeasurement:
    inner = _inner_width(width_emu)
    indent = theme.spacing.card_padding_emu
    item_gap = theme.spacing.sm_emu
    item_width = max(1, inner - indent)
    body = body_typography(theme)
    items = _as_text_tuple(block.fields.get("items"))
    parts = [
        _TextPart(
            f"item{index}.text",
            measure_text(
                item,
                available_width_emu=item_width,
                theme=theme,
                font_size_pt=body.size_pt,
                weight=body.weight,
                tracking_em=body.tracking_em,
            ),
        )
        for index, item in enumerate(items, start=1)
    ]
    if not parts:
        parts.append(
            _TextPart(
                "item1.text",
                measure_text(
                    "",
                    available_width_emu=item_width,
                    theme=theme,
                    font_size_pt=body.size_pt,
                    weight=body.weight,
                    tracking_em=body.tracking_em,
                ),
            )
        )
    combined = _combine_parts(parts)
    gap_height = item_gap * (len(parts) - 1)
    measurement = TextMeasurement(
        width_emu=combined.width_emu,
        height_emu=combined.height_emu + gap_height,
        line_count=combined.line_count,
        overflow_width_emu=combined.overflow_width_emu,
    )
    return _with_padding(
        measurement,
        width_leaf=_overflow_width_leaf(parts),
        height_leaf=_height_leaf(parts),
    )


def _measure_quote_block(block: BlockIR, *, width_emu: int, theme: Theme) -> BlockMeasurement:
    inner = _inner_width(width_emu, padding_emu=theme.card.padding_emu)
    body = body_typography(theme)
    parts = [
        _TextPart(
            "text",
            measure_text(
                _as_text(block.fields.get("text")),
                available_width_emu=inner,
                theme=theme,
                font_size_pt=body.size_pt,
                weight=body.weight,
                tracking_em=body.tracking_em,
            ),
        )
    ]
    attribution = _as_text(block.fields.get("attribution"))
    if attribution:
        attribution_style = body_typography(theme, weight=theme.typography.weights[1])
        parts.append(
            _TextPart(
                "attribution",
                measure_text(
                    attribution,
                    available_width_emu=inner,
                    theme=theme,
                    font_size_pt=attribution_style.size_pt,
                    weight=attribution_style.weight,
                    tracking_em=attribution_style.tracking_em,
                ),
            )
        )
    return _measure_parts(parts, theme=theme, padding_emu=theme.card.padding_emu)


def _measure_metric_block(block: BlockIR, *, width_emu: int, theme: Theme) -> BlockMeasurement:
    inner = _inner_width(width_emu, padding_emu=theme.card.padding_emu)
    typography = theme.typography
    parts: list[_TextPart] = []
    value = _as_text(block.fields.get("value"))
    if value:
        parts.append(
            _TextPart(
                "value",
                measure_text(
                    value,
                    available_width_emu=inner,
                    theme=theme,
                    font_size_pt=max(typography.metric_pt, typography.minimum_pt),
                    weight=typography.weights[3],
                    tracking_em=typography.tracking_em,
                ),
            )
        )
    label = _as_text(block.fields.get("label"))
    if label:
        parts.append(
            _TextPart(
                "label",
                measure_text(
                    label,
                    available_width_emu=inner,
                    theme=theme,
                    font_size_pt=max(typography.label_pt, typography.minimum_pt),
                    weight=typography.weights[1],
                    tracking_em=typography.tracking_em,
                ),
            )
        )
    if not parts:
        body = body_typography(theme)
        value_part = _TextPart(
            "value",
            measure_text(
                "",
                available_width_emu=inner,
                theme=theme,
                font_size_pt=body.size_pt,
                weight=body.weight,
                tracking_em=body.tracking_em,
            ),
        )
        return _with_padding(_combine_parts([value_part]), padding_emu=theme.card.padding_emu)
    return _measure_parts(parts, theme=theme, padding_emu=theme.card.padding_emu)


def _measure_code_block(block: BlockIR, *, width_emu: int, theme: Theme) -> BlockMeasurement:
    inner = _inner_width(width_emu, padding_emu=theme.spacing.card_padding_emu)
    code = _as_text(block.fields.get("code"))
    # Renderer memakai default ``True`` saat field line_numbers tidak ada.
    code_width = code_text_width(
        code,
        inner_width_emu=inner,
        theme=theme,
        line_numbers=bool(block.fields.get("line_numbers", True)),
    )
    parts = [
        _TextPart(
            "code",
            measure_code_text(
                code,
                available_width_emu=code_width,
                theme=theme,
            ),
        )
    ]
    filename = _as_text(block.fields.get("filename"))
    filename_gap = 0
    if filename:
        parts.insert(
            0,
            _TextPart(
                "filename",
                measure_text(
                    filename,
                    available_width_emu=inner,
                    theme=theme,
                    font_size_pt=max(theme.code.filename_pt, theme.typography.minimum_pt),
                    weight=theme.typography.weights[1],
                    tracking_em=theme.typography.tracking_em,
                ),
            ),
        )
        filename_gap = theme.spacing.sm_emu
    combined = _combine_parts(parts)
    if filename_gap:
        combined = TextMeasurement(
            width_emu=combined.width_emu,
            height_emu=combined.height_emu + filename_gap,
            line_count=combined.line_count,
            overflow_width_emu=combined.overflow_width_emu,
        )
    return _with_padding(
        combined,
        padding_emu=theme.spacing.card_padding_emu,
        width_leaf=_overflow_width_leaf(parts),
        height_leaf=_height_leaf(parts),
    )


def table_cell_padding_emu(theme: Theme) -> int:
    """Padding sel tabel per sisi dalam EMU (token ``spacing.md``)."""
    return theme.spacing.md_emu


def table_column_widths(
    columns: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    table_width_emu: int,
    theme: Theme,
    emphasis_column: int | None = None,
) -> tuple[int, ...]:
    """Hitung lebar kolom tabel yang sadar konten dan selalu presisi total.

    Lebar alami tiap kolom adalah teks terlebar ditambah padding kiri-kanan.
    Nilai dijepit ke minimum 40 px dan maksimum 40% lebar tabel, lalu sisa
    lebar dibagi rata ke kolom yang belum mencapai batas maksimum. Bila semua
    kolom sudah mencapai batas, sisa dibagi rata agar tabel tetap memenuhi
    lebar slot.
    """
    column_count = max(len(columns), max((len(row) for row in rows), default=0))
    if column_count <= 0:
        return ()
    if table_width_emu <= 0:
        raise MeasurementError("Lebar tabel harus positif.")
    padding = 2 * table_cell_padding_emu(theme)
    minimum = min(_TABLE_COLUMN_MIN_EMU, max(1, table_width_emu // column_count))
    maximum = max(minimum, round(table_width_emu * _TABLE_COLUMN_MAX_FRACTION))
    header_style = body_typography(theme, weight=theme.typography.weights[1])
    body_style = body_typography(theme)
    natural: list[int] = []
    for column_index in range(column_count):
        widths: list[int] = []
        if column_index < len(columns):
            widths.append(
                measure_text(
                    columns[column_index],
                    available_width_emu=_TABLE_NATURAL_WIDTH_EMU,
                    theme=theme,
                    font_size_pt=header_style.size_pt,
                    weight=(
                        theme.typography.weights[2]
                        if emphasis_column == column_index + 1
                        else header_style.weight
                    ),
                    tracking_em=header_style.tracking_em,
                ).width_emu
            )
        for row in rows:
            if column_index < len(row):
                widths.append(
                    measure_text(
                        row[column_index],
                        available_width_emu=_TABLE_NATURAL_WIDTH_EMU,
                        theme=theme,
                        font_size_pt=body_style.size_pt,
                        weight=(
                            theme.typography.weights[1]
                            if emphasis_column == column_index + 1
                            else body_style.weight
                        ),
                        tracking_em=body_style.tracking_em,
                    ).width_emu
                )
        natural.append(max(widths, default=0) + padding)

    weights = [max(width, minimum) for width in natural]
    total = sum(weights)
    allocated = [
        min(max(round(table_width_emu * weight / total), minimum), maximum) for weight in weights
    ]
    remaining = table_width_emu - sum(allocated)
    if remaining < 0:
        scale = table_width_emu / sum(allocated)
        allocated = [max(1, round(width * scale)) for width in allocated]
        remaining = table_width_emu - sum(allocated)
    while remaining > 0:
        below_maximum = [index for index, width in enumerate(allocated) if width < maximum]
        recipients = below_maximum or list(range(column_count))
        share = max(1, remaining // len(recipients))
        for index in recipients:
            if remaining <= 0:
                break
            room = maximum - allocated[index] if below_maximum else remaining
            addition = min(share, remaining, room)
            if addition <= 0:
                continue
            allocated[index] += addition
            remaining -= addition
    if remaining != 0:
        allocated[-1] += remaining
    return tuple(allocated)


def _measure_table_block(block: BlockIR, *, width_emu: int, theme: Theme) -> BlockMeasurement:
    inner = _inner_width(width_emu)
    columns = _as_text_tuple(block.fields.get("columns"))
    rows = _as_text_rows(block.fields.get("rows"))
    cell_padding = table_cell_padding_emu(theme)
    row_margin = 2 * cell_padding

    cell_parts: list[_TextPart] = []
    table_height = 0
    table_width = 0
    table_lines = 0
    table_overflow = 0
    row_column_count = max((len(row) for row in rows), default=0)
    column_count = max(len(columns), row_column_count)
    if column_count > 0:
        emphasis_column = _emphasis_column(block.fields, column_count=column_count)
        column_widths = table_column_widths(
            columns,
            rows,
            table_width_emu=inner,
            theme=theme,
            emphasis_column=emphasis_column,
        )
        cell_widths = tuple(max(1, width - 2 * cell_padding) for width in column_widths)
        header_style = body_typography(theme, weight=theme.typography.weights[1])
        body_style = body_typography(theme)
        if columns:
            header_parts = [
                _TextPart(
                    f"h{column_index}",
                    measure_text(
                        cell,
                        available_width_emu=cell_widths[column_index - 1],
                        theme=theme,
                        font_size_pt=header_style.size_pt,
                        weight=(
                            theme.typography.weights[2]
                            if emphasis_column == column_index
                            else header_style.weight
                        ),
                        tracking_em=header_style.tracking_em,
                    ),
                )
                for column_index, cell in enumerate(columns, start=1)
            ]
            cell_parts.extend(header_parts)
            table_height += max(item.measurement.height_emu for item in header_parts) + row_margin
            table_width = max(
                table_width,
                max(item.measurement.width_emu + 2 * cell_padding for item in header_parts),
            )
            table_lines += sum(item.measurement.line_count for item in header_parts)
            table_overflow = max(
                table_overflow,
                max(item.measurement.overflow_width_emu for item in header_parts),
            )
        for row_index, row in enumerate(rows, start=1):
            row_parts = [
                _TextPart(
                    f"r{row_index}.c{column_index}",
                    measure_text(
                        cell,
                        available_width_emu=cell_widths[column_index - 1],
                        theme=theme,
                        font_size_pt=body_style.size_pt,
                        weight=(
                            theme.typography.weights[1]
                            if emphasis_column == column_index
                            else body_style.weight
                        ),
                        tracking_em=body_style.tracking_em,
                    ),
                )
                for column_index, cell in enumerate(row, start=1)
            ]
            if not row_parts:
                continue
            cell_parts.extend(row_parts)
            table_height += max(item.measurement.height_emu for item in row_parts) + row_margin
            table_width = max(
                table_width,
                max(item.measurement.width_emu + 2 * cell_padding for item in row_parts),
            )
            table_lines += sum(item.measurement.line_count for item in row_parts)
            table_overflow = max(
                table_overflow,
                max(item.measurement.overflow_width_emu for item in row_parts),
            )

    if not cell_parts:
        return _with_padding(
            TextMeasurement(width_emu=0, height_emu=0, line_count=0, overflow_width_emu=0)
        )

    width = max((part.measurement.width_emu for part in cell_parts), default=0)
    overflow_width = max(
        (part.measurement.overflow_width_emu for part in cell_parts),
        default=0,
    )
    return _with_padding(
        TextMeasurement(
            width_emu=width,
            height_emu=table_height,
            line_count=table_lines,
            overflow_width_emu=overflow_width,
        ),
        width_leaf=_overflow_width_leaf(cell_parts),
        height_leaf=_height_leaf(cell_parts),
    )


def _measure_media_block(
    block: BlockIR,
    *,
    width_emu: int,
    theme: Theme,
    max_height_emu: int | None = None,
) -> BlockMeasurement:
    minimum_media_height = theme.spacing.md_emu
    natural_height = max(minimum_media_height, width_emu * 9 // 16)
    if max_height_emu is None:
        media_height = natural_height
        overflow_height = 0
    else:
        available_height = max(0, max_height_emu)
        media_height = min(natural_height, max(minimum_media_height, available_height))
        overflow_height = max(0, media_height - available_height)
    return BlockMeasurement(
        width_emu=width_emu,
        height_emu=media_height,
        line_count=0,
        overflow_width_emu=0,
        overflow_height_emu=overflow_height,
    )


def _measure_parts(
    parts: Sequence[_TextPart], *, theme: Theme, padding_emu: int = 0
) -> BlockMeasurement:
    return _with_padding(
        _combine_parts(parts),
        padding_emu=padding_emu,
        width_leaf=_overflow_width_leaf(parts),
        height_leaf=_height_leaf(parts),
    )


def _combine_parts(parts: Sequence[_TextPart]) -> TextMeasurement:
    return _combine_text([part.measurement for part in parts])


def _overflow_width_leaf(parts: Sequence[_TextPart]) -> str | None:
    overflowing = [part for part in parts if part.measurement.overflow_width_emu > 0]
    if not overflowing:
        return None
    return max(overflowing, key=lambda part: part.measurement.overflow_width_emu).leaf


def _height_leaf(parts: Sequence[_TextPart]) -> str | None:
    if not parts:
        return None
    return max(parts, key=lambda part: part.measurement.height_emu).leaf


def _combine_text(measurements: Sequence[TextMeasurement]) -> TextMeasurement:
    if not measurements:
        return TextMeasurement(
            width_emu=0,
            height_emu=0,
            line_count=0,
            overflow_width_emu=0,
        )
    return TextMeasurement(
        width_emu=max(item.width_emu for item in measurements),
        height_emu=sum(item.height_emu for item in measurements),
        line_count=sum(item.line_count for item in measurements),
        overflow_width_emu=max(item.overflow_width_emu for item in measurements),
    )


def _with_padding(
    measurement: TextMeasurement,
    *,
    padding_emu: int = 0,
    width_leaf: str | None = None,
    height_leaf: str | None = None,
) -> BlockMeasurement:
    return BlockMeasurement(
        width_emu=measurement.width_emu,
        height_emu=measurement.height_emu + 2 * padding_emu,
        line_count=measurement.line_count,
        overflow_width_emu=measurement.overflow_width_emu,
        overflow_width_leaf=width_leaf,
        height_leaf=height_leaf,
    )


def _inner_width(width_emu: int, *, padding_emu: int = 0) -> int:
    return max(1, width_emu - 2 * padding_emu)


def _emphasis_column(fields: Mapping[str, object], *, column_count: int) -> int | None:
    """Baca kolom emphasis 1-based bila valid untuk jumlah kolom tabel."""
    value = fields.get("emphasis_column")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if 1 <= value <= column_count:
        return value
    return None


def role_typography(
    theme: Theme,
    role: str | None,
    *,
    layout_id: str | None = None,
) -> RoleTypography:
    """Petakan role teks ke ukuran, bobot, dan tracking token.

    ``layout_id`` opsional membedakan judul cover dari judul konten. Layout
    yang tidak memiliki konteks ini tetap memakai ``title_pt`` supaya
    pengukuran dan render tidak berbeda tanpa bukti geometri.
    """
    typography = theme.typography
    active_role = role if role in _ROLE_NAMES else "body"
    weights = typography.weights
    if active_role == "display":
        size_pt = typography.display_pt
        weight = weights[3]
        tracking_em = typography.tracking_em
    elif active_role == "title":
        size_pt = typography.cover_title_pt if layout_id == "cover" else typography.title_pt
        weight = weights[2]
        tracking_em = typography.tracking_em
    elif active_role == "lead":
        size_pt = typography.lead_pt
        weight = weights[1]
        tracking_em = typography.tracking_em
    elif active_role == "caption":
        size_pt = typography.caption_pt
        weight = weights[0]
        tracking_em = typography.tracking_em
    elif active_role == "label":
        size_pt = typography.label_pt
        weight = weights[1]
        tracking_em = typography.tracking_em
    elif active_role == "kicker":
        size_pt = typography.caption_pt
        weight = weights[2]
        tracking_em = typography.kicker_tracking_em
    else:
        size_pt = typography.body_pt
        weight = weights[0]
        tracking_em = typography.tracking_em
    return RoleTypography(
        size_pt=max(size_pt, typography.minimum_pt),
        weight=weight,
        tracking_em=tracking_em,
    )


def body_typography(theme: Theme, *, weight: int | None = None) -> RoleTypography:
    """Tipografi body dengan bobot opsional dari tuple token weights."""
    typography = theme.typography
    return RoleTypography(
        size_pt=max(typography.body_pt, typography.minimum_pt),
        weight=typography.weights[0] if weight is None else weight,
        tracking_em=typography.tracking_em,
    )


def _code_chunks(line: str, capacity: int) -> tuple[str, ...]:
    if not line:
        return ("",)
    return tuple(line[index : index + capacity] for index in range(0, len(line), capacity))


def _round_emu(value: float) -> int:
    return round(value)


@lru_cache(maxsize=len(_FONT_BY_WEIGHT))
def _load_font(file_name: str) -> ImageFont.FreeTypeFont:
    path: Path = font_path(file_name)
    return ImageFont.truetype(str(path), _FONT_PIXEL_SIZE)


def _font_file_for_weight(weight: int) -> str:
    return min(_FONT_BY_WEIGHT, key=lambda item: (abs(item[0] - weight), item[0]))[1]


def _line_width_emu(
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    scale: float,
    tracking_emu: float,
) -> int:
    if not text:
        return 0
    advance = font.getlength(text) * scale
    tracking = max(0, len(text) - 1) * tracking_emu
    return max(0, _round_emu(advance + tracking))


def _wrap_text(
    text: str,
    *,
    width_emu: int,
    font: ImageFont.FreeTypeFont,
    scale: float,
    tracking_emu: float,
) -> tuple[tuple[str, ...], int]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    overflow = 0
    for paragraph in normalized.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            candidate_width = _line_width_emu(
                candidate,
                font=font,
                scale=scale,
                tracking_emu=tracking_emu,
            )
            if candidate_width <= width_emu:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            word_width = _line_width_emu(
                word,
                font=font,
                scale=scale,
                tracking_emu=tracking_emu,
            )
            if word_width > width_emu:
                lines.append(word)
                overflow = max(overflow, word_width - width_emu)
            else:
                current = word
        if current:
            lines.append(current)
    if not lines:
        lines.append("")
    widths = [
        _line_width_emu(
            line,
            font=font,
            scale=scale,
            tracking_emu=tracking_emu,
        )
        for line in lines
    ]
    overflow = max(overflow, max(widths, default=0) - width_emu)
    return tuple(lines), overflow


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _as_text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        values = cast("list[object]", value)
        return tuple(_as_text(item) for item in values)
    if isinstance(value, tuple):
        tuple_values = cast("tuple[object, ...]", value)
        return tuple(_as_text(item) for item in tuple_values)
    return ()


def _as_text_rows(value: object) -> tuple[tuple[str, ...], ...]:
    if isinstance(value, list):
        values = cast("list[object]", value)
        return tuple(_as_text_tuple(row) for row in values)
    if isinstance(value, tuple):
        tuple_values = cast("tuple[object, ...]", value)
        return tuple(_as_text_tuple(row) for row in tuple_values)
    return ()

"""Test pengukuran teks dan block memakai metrik font bundle."""

from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest

import autooffice.deck.layout.measure as measure
from autooffice.deck.layout.measure import (
    MeasurementError,
    TextMeasurement,
    measure_block,
    measure_code_text,
    measure_text,
    table_cell_padding_emu,
    table_column_widths,
)
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.design.fonts import FONT_DIR
from autooffice.design.theme import Theme

WIDTH = 2_000_000


def test_font_weight_mapping_uses_packaged_liberation_sans() -> None:
    regular = measure._font_file_for_weight(400)
    bold = measure._font_file_for_weight(700)

    assert regular == "LiberationSans-Regular.ttf"
    assert bold == "LiberationSans-Bold.ttf"
    assert measure.font_path(regular) == FONT_DIR / regular
    assert measure.font_path(bold) == FONT_DIR / bold
    assert measure._load_font(regular).path == str(FONT_DIR / regular)
    assert measure._load_font(bold).path == str(FONT_DIR / bold)


def test_missing_packaged_font_raises_instead_of_falling_back(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("autooffice.design.fonts.FONT_DIR", tmp_path / "absent")
    measure._load_font.cache_clear()
    try:
        with pytest.raises(OSError, match="cannot open resource"):
            measure._load_font("LiberationSans-Regular.ttf")
    finally:
        measure._load_font.cache_clear()


def test_text_measurement_uses_theme_line_height(theme: Theme) -> None:
    measurement = measure_text("Halo", available_width_emu=WIDTH, theme=theme)
    expected_line_height = round(round(theme.typography.body_pt * 12_700) * 1.2)

    assert isinstance(measurement, TextMeasurement)
    assert measurement.line_count == 1
    assert measurement.height_emu == expected_line_height
    assert measurement.width_emu > 0
    assert measurement.overflow_width_emu == 0


def test_text_wraps_without_shrinking(theme: Theme) -> None:
    text = " ".join(["kata"] * 100)
    measurement = measure_text(text, available_width_emu=350_000, theme=theme)
    line_height = round(round(theme.typography.body_pt * 12_700) * 1.2)

    assert measurement.line_count > 1
    assert measurement.height_emu == measurement.line_count * line_height


def test_long_word_is_flagged_instead_of_ellipsized(theme: Theme) -> None:
    measurement = measure_text("W" * 40, available_width_emu=100_000, theme=theme)

    assert measurement.line_count == 1
    assert measurement.overflow_width_emu > 0
    assert measurement.width_emu > 100_000


def test_explicit_newlines_add_lines(theme: Theme) -> None:
    measurement = measure_text("satu\ndua\ntiga", available_width_emu=WIDTH, theme=theme)

    assert measurement.line_count == 3


def test_negative_tracking_is_applied(theme: Theme) -> None:
    normal = measure_text("Tracking test", available_width_emu=WIDTH, theme=theme, tracking_em=0.0)
    tight = measure_text("Tracking test", available_width_emu=WIDTH, theme=theme, tracking_em=-0.1)

    assert tight.width_emu < normal.width_emu


def test_text_block_height_has_no_phantom_padding(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("body", "text", fields={"text": "Satu baris"}, role="body")
    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    text = measure_text(
        "Satu baris",
        available_width_emu=WIDTH,
        theme=theme,
    )

    assert measurement.height_emu == text.height_emu
    assert measurement.overflow_width_emu == 0


def test_code_height_grows_with_lines(block_factory: Callable[..., BlockIR], theme: Theme) -> None:
    short = block_factory("code1", "code", fields={"code": "x = 1"})
    long = block_factory("code2", "code", fields={"code": "\n".join(["x = 1"] * 20)})

    assert (
        measure_block(long, width_emu=WIDTH, theme=theme).height_emu
        > measure_block(short, width_emu=WIDTH, theme=theme).height_emu
    )


def test_table_height_grows_with_rows(block_factory: Callable[..., BlockIR], theme: Theme) -> None:
    short = block_factory(
        "table1",
        "table",
        fields={"columns": ("A", "B"), "rows": (("1", "2"),)},
    )
    long = block_factory(
        "table2",
        "table",
        fields={
            "columns": ("A", "B"),
            "rows": tuple((str(index), str(index + 1)) for index in range(8)),
        },
    )

    assert (
        measure_block(long, width_emu=WIDTH, theme=theme).height_emu
        > measure_block(short, width_emu=WIDTH, theme=theme).height_emu
    )


def test_table_and_code_wide_content_is_flagged(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    table = block_factory(
        "table1",
        "table",
        fields={"columns": ("A",), "rows": (("W" * 200,),)},
    )
    code = block_factory("code1", "code", fields={"code": "W" * 400})

    assert measure_block(table, width_emu=400_000, theme=theme).overflow_width_emu > 0
    assert measure_block(code, width_emu=400_000, theme=theme).overflow_width_emu > 0


def test_text_ignores_max_height(block_factory: Callable[..., BlockIR], theme: Theme) -> None:
    block = block_factory("body", "text", fields={"text": "Satu baris"}, role="body")
    natural = measure_block(block, width_emu=WIDTH, theme=theme)
    capped = measure_block(
        block,
        width_emu=WIDTH,
        theme=theme,
        max_height_emu=theme.spacing.sm_emu,
    )

    assert capped == natural
    assert capped.overflow_height_emu == 0


def test_media_height_is_capped_to_max_height(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("image1", "image", fields={"path": "assets/hero.png"})
    natural = measure_block(block, width_emu=WIDTH, theme=theme)
    capped = measure_block(
        block,
        width_emu=WIDTH,
        theme=theme,
        max_height_emu=900_000,
    )

    assert natural.height_emu == WIDTH * 9 // 16
    assert capped.height_emu == 900_000
    assert capped.overflow_height_emu == 0


def test_media_height_never_drops_below_minimum(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("image1", "image", fields={"path": "assets/hero.png"})
    max_height = theme.spacing.md_emu // 2
    measurement = measure_block(
        block,
        width_emu=WIDTH,
        theme=theme,
        max_height_emu=max_height,
    )

    assert measurement.height_emu == theme.spacing.md_emu
    assert measurement.overflow_height_emu == theme.spacing.md_emu - max_height


def test_zero_measurement_width_is_rejected(theme: Theme) -> None:
    with pytest.raises(MeasurementError, match="positif"):
        measure_text("Halo", available_width_emu=0, theme=theme)


def _content_width(width: int = WIDTH) -> int:
    return width


def _inner_width(theme: Theme, width: int = WIDTH) -> int:
    return width - 2 * theme.spacing.card_padding_emu


@pytest.mark.parametrize(
    ("role", "size_token", "weight", "tracking_token"),
    [
        ("display", "display_pt", 800, "tracking_em"),
        ("title", "title_pt", 700, "tracking_em"),
        ("lead", "lead_pt", 600, "tracking_em"),
        ("body", "body_pt", 400, "tracking_em"),
        ("caption", "caption_pt", 400, "tracking_em"),
        ("label", "label_pt", 600, "tracking_em"),
        ("kicker", "caption_pt", 700, "kicker_tracking_em"),
    ],
)
def test_text_role_matches_renderer_size_and_weight(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
    role: str,
    size_token: str,
    weight: int,
    tracking_token: str,
) -> None:
    block = block_factory("body", "text", fields={"text": "Halo dunia"}, role=role)
    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    expected = measure_text(
        "Halo dunia",
        available_width_emu=_content_width(),
        theme=theme,
        font_size_pt=getattr(theme.typography, size_token),
        weight=weight,
        tracking_em=getattr(theme.typography, tracking_token),
    )

    assert measurement.height_emu == expected.height_emu
    assert measurement.width_emu == expected.width_emu


@pytest.mark.parametrize(
    ("lighter_role", "heavier_role"),
    [
        ("body", "lead"),
        ("caption", "label"),
    ],
)
def test_role_weight_affects_measured_width(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
    lighter_role: str,
    heavier_role: str,
) -> None:
    lighter = block_factory(
        "lighter",
        "text",
        fields={"text": "Halo dunia"},
        role=lighter_role,
    )
    heavier = block_factory(
        "heavier",
        "text",
        fields={"text": "Halo dunia"},
        role=heavier_role,
    )

    lighter_measurement = measure_block(lighter, width_emu=WIDTH, theme=theme)
    heavier_measurement = measure_block(heavier, width_emu=WIDTH, theme=theme)

    assert heavier_measurement.width_emu > lighter_measurement.width_emu


@pytest.mark.parametrize(
    ("size_pt", "lighter_weight", "heavier_weight"),
    [
        (30.0, 600, 700),
        (12.5, 700, 800),
    ],
)
def test_bold_weight_tiers_share_arial_bold_metrics(
    theme: Theme,
    size_pt: float,
    lighter_weight: int,
    heavier_weight: int,
) -> None:
    lighter = measure_text(
        "Halo dunia",
        available_width_emu=WIDTH,
        theme=theme,
        font_size_pt=size_pt,
        weight=lighter_weight,
    )
    heavier = measure_text(
        "Halo dunia",
        available_width_emu=WIDTH,
        theme=theme,
        font_size_pt=size_pt,
        weight=heavier_weight,
    )

    assert lighter == heavier


def test_role_typography_distinguishes_cover_title(theme: Theme) -> None:
    cover = measure.role_typography(theme, "title", layout_id="cover")
    content = measure.role_typography(theme, "title")

    assert cover.size_pt == theme.typography.cover_title_pt
    assert content.size_pt == theme.typography.title_pt


def test_role_typography_weights_come_from_theme_tuple(theme: Theme) -> None:
    custom = replace(
        theme,
        typography=replace(theme.typography, weights=(300, 500, 650, 900)),
    )

    assert measure.role_typography(custom, "display").weight == 900
    assert measure.role_typography(custom, "title").weight == 650
    assert measure.role_typography(custom, "lead").weight == 500
    assert measure.role_typography(custom, "body").weight == 300


def test_kicker_uses_positive_tracking(theme: Theme) -> None:
    kicker = measure.role_typography(theme, "kicker")

    assert kicker.tracking_em > 0
    assert kicker.size_pt == theme.typography.caption_pt


def test_code_filename_height_includes_gap(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
) -> None:
    code_text = "def key():\n    return 1"
    filename = "keys.py"
    block = block_factory(
        "code1",
        "code",
        fields={"code": code_text, "filename": filename},
    )
    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    code = measure_code_text(
        code_text,
        available_width_emu=_inner_width(theme),
        theme=theme,
    )
    filename_measurement = measure_text(
        filename,
        available_width_emu=_inner_width(theme),
        theme=theme,
        font_size_pt=max(theme.code.filename_pt, theme.typography.minimum_pt),
        weight=theme.typography.weights[1],
    )

    assert measurement.height_emu == (
        code.height_emu
        + filename_measurement.height_emu
        + theme.spacing.sm_emu
        + 2 * theme.spacing.card_padding_emu
    )
    assert measurement.line_count == code.line_count + filename_measurement.line_count


def test_code_preserves_leading_and_repeated_spaces(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
) -> None:
    plain = block_factory("plain", "code", fields={"code": "x = 1"})
    indented = block_factory("indented", "code", fields={"code": "    x = 1"})
    spaced = block_factory("spaced", "code", fields={"code": "x  =  1"})

    plain_measurement = measure_block(plain, width_emu=WIDTH, theme=theme)
    indented_measurement = measure_block(indented, width_emu=WIDTH, theme=theme)
    spaced_measurement = measure_block(spaced, width_emu=WIDTH, theme=theme)

    assert indented_measurement.width_emu > plain_measurement.width_emu
    assert spaced_measurement.width_emu > plain_measurement.width_emu
    assert indented_measurement.line_count == 1
    assert spaced_measurement.line_count == 1


def test_indented_code_near_slot_width_reports_wrapped_line_count(theme: Theme) -> None:
    inner = _inner_width(theme)
    character_width = measure_code_text(
        "x",
        available_width_emu=inner,
        theme=theme,
    ).width_emu
    capacity = inner // character_width
    unindented = "x" * capacity
    indented = "    " + unindented

    unindented_measurement = measure_code_text(
        unindented,
        available_width_emu=inner,
        theme=theme,
    )
    indented_measurement = measure_code_text(
        indented,
        available_width_emu=inner,
        theme=theme,
    )

    assert unindented_measurement.line_count == 1
    assert indented_measurement.line_count == 2
    assert indented_measurement.width_emu <= inner


def test_table_emphasis_column_uses_emphasized_weights(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
) -> None:
    header = "review eksperimen delta tambahan hasil"
    body = "arsitektur column arsitektur kontrak measurement arsitektur"
    width = 4_000_000
    block = block_factory(
        "table1",
        "table",
        fields={
            "columns": ("A", header),
            "rows": (("1", body), ("2", body)),
            "emphasis_column": 2,
        },
    )
    inner = width
    padding = table_cell_padding_emu(theme)
    column_widths = table_column_widths(
        ("A", header),
        (("1", body), ("2", body)),
        table_width_emu=inner,
        theme=theme,
        emphasis_column=2,
    )
    cell_width = column_widths[1] - 2 * padding
    size_pt = max(theme.typography.body_pt, theme.typography.minimum_pt)

    def measure(text: str, weight: int) -> TextMeasurement:
        return measure_text(
            text,
            available_width_emu=cell_width,
            theme=theme,
            font_size_pt=size_pt,
            weight=weight,
        )

    header_emphasis = measure(header, theme.typography.weights[2])
    body_emphasis = measure(body, theme.typography.weights[1])
    assert header_emphasis.width_emu >= measure(header, theme.typography.weights[1]).width_emu
    assert body_emphasis.width_emu >= measure(body, theme.typography.weights[0]).width_emu
    margin = 2 * padding

    measurement = measure_block(block, width_emu=width, theme=theme)

    expected_height = header_emphasis.height_emu + margin + 2 * (body_emphasis.height_emu + margin)
    assert measurement.height_emu == expected_height


def test_table_height_includes_cell_margins(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
) -> None:
    columns = ("A", "B")
    rows = (("1", "2"), ("3", "4"))
    block = block_factory(
        "table1",
        "table",
        fields={"columns": columns, "rows": rows},
    )

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    padding = table_cell_padding_emu(theme)
    column_widths = table_column_widths(
        columns,
        rows,
        table_width_emu=WIDTH,
        theme=theme,
    )
    cell_widths = [column_width - 2 * padding for column_width in column_widths]
    header = measure_text(
        columns[0],
        available_width_emu=cell_widths[0],
        theme=theme,
        weight=theme.typography.weights[1],
    )
    cell = measure_text(
        rows[0][0],
        available_width_emu=cell_widths[0],
        theme=theme,
        weight=theme.typography.weights[0],
    )

    expected_height = header.height_emu + 2 * padding + 2 * (cell.height_emu + 2 * padding)

    assert measurement.height_emu == expected_height


@pytest.fixture
def measure_caches() -> Iterator[None]:
    """Kosongkan cache pengukuran sebelum dan sesudah test cache."""
    measure._measure_text_cached.cache_clear()
    measure._measure_code_text_cached.cache_clear()
    yield
    measure._measure_text_cached.cache_clear()
    measure._measure_code_text_cached.cache_clear()


def test_text_measurement_cache_hit_returns_equal_result(
    theme: Theme, measure_caches: None
) -> None:
    first = measure_text("Halo dunia", available_width_emu=WIDTH, theme=theme)
    second = measure_text("Halo dunia", available_width_emu=WIDTH, theme=theme)
    info = measure._measure_text_cached.cache_info()

    assert second == first
    assert info.hits == 1
    assert info.misses == 1
    assert info.currsize == 1


@pytest.mark.parametrize(
    ("text", "overrides"),
    [
        pytest.param("Teks lain", {}, id="text"),
        pytest.param("Halo dunia", {"available_width_emu": WIDTH + 1}, id="width"),
        pytest.param("Halo dunia", {"font_size_pt": 17.0}, id="font-size"),
        pytest.param("Halo dunia", {"weight": 700}, id="weight"),
        pytest.param("Halo dunia", {"line_height": 1.5}, id="line-height"),
        pytest.param("Halo dunia", {"tracking_em": 0.03}, id="tracking"),
    ],
)
def test_text_measurement_cache_key_covers_each_input(
    theme: Theme,
    measure_caches: None,
    text: str,
    overrides: dict[str, int | float],
) -> None:
    base_arguments: dict[str, int | float] = {"available_width_emu": WIDTH}
    variant_arguments = base_arguments | overrides

    measure_text("Halo dunia", theme=theme, **base_arguments)
    measure_text(text, theme=theme, **variant_arguments)
    info = measure._measure_text_cached.cache_info()

    assert info.misses == 2
    assert info.currsize == 2


def test_text_measurement_cache_uses_resolved_theme_values(
    theme: Theme, measure_caches: None
) -> None:
    alternate = replace(
        theme,
        typography=replace(theme.typography, body_pt=theme.typography.body_pt + 2),
    )

    default = measure_text("Halo dunia", available_width_emu=WIDTH, theme=theme)
    resized = measure_text("Halo dunia", available_width_emu=WIDTH, theme=alternate)
    info = measure._measure_text_cached.cache_info()

    assert resized != default
    assert info.misses == 2
    assert info.currsize == 2


def test_code_measurement_cache_hit_returns_equal_result(
    theme: Theme, measure_caches: None
) -> None:
    first = measure_code_text("x = 1", available_width_emu=WIDTH, theme=theme)
    second = measure_code_text("x = 1", available_width_emu=WIDTH, theme=theme)
    info = measure._measure_code_text_cached.cache_info()

    assert second == first
    assert info.hits == 1
    assert info.misses == 1
    assert info.currsize == 1


@pytest.mark.parametrize(
    ("text", "overrides"),
    [
        pytest.param("y = 2", {}, id="text"),
        pytest.param("x = 1", {"available_width_emu": WIDTH + 1}, id="width"),
        pytest.param("x = 1", {"font_size_pt": 18.0}, id="font-size"),
        pytest.param("x = 1", {"line_height": 1.5}, id="line-height"),
    ],
)
def test_code_measurement_cache_key_covers_each_input(
    theme: Theme,
    measure_caches: None,
    text: str,
    overrides: dict[str, int | float],
) -> None:
    base_arguments: dict[str, int | float] = {"available_width_emu": WIDTH}
    variant_arguments = base_arguments | overrides

    measure_code_text("x = 1", theme=theme, **base_arguments)
    measure_code_text(text, theme=theme, **variant_arguments)
    info = measure._measure_code_text_cached.cache_info()

    assert info.misses == 2
    assert info.currsize == 2


def test_measurement_caches_have_bounded_maxsize() -> None:
    text_maxsize = measure._measure_text_cached.cache_parameters()["maxsize"]
    code_maxsize = measure._measure_code_text_cached.cache_parameters()["maxsize"]

    assert text_maxsize == measure._MEASURE_CACHE_MAXSIZE
    assert code_maxsize == measure._MEASURE_CACHE_MAXSIZE
    assert measure._MEASURE_CACHE_MAXSIZE > 0


def test_text_measurement_cache_evicts_when_full(theme: Theme, measure_caches: None) -> None:
    cache = measure._measure_text_cached
    maxsize = cache.cache_parameters()["maxsize"]
    assert isinstance(maxsize, int)

    for index in range(maxsize + 1):
        measure_text(str(index), available_width_emu=WIDTH, theme=theme)

    info = cache.cache_info()

    assert info.currsize == maxsize
    assert info.misses == maxsize + 1


def test_code_measurement_cache_evicts_when_full(theme: Theme, measure_caches: None) -> None:
    cache = measure._measure_code_text_cached
    maxsize = cache.cache_parameters()["maxsize"]
    assert isinstance(maxsize, int)

    for index in range(maxsize + 1):
        measure_code_text(str(index), available_width_emu=WIDTH, theme=theme)

    info = cache.cache_info()

    assert info.currsize == maxsize
    assert info.misses == maxsize + 1

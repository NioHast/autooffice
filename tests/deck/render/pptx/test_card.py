"""Tes card metric/quote: geometri, fill tanpa garis, dan paritas measure."""

import pytest
from _edge_helpers import new_slide
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_FILL
from pptx.oxml.ns import qn

from autooffice.deck.layout.measure import measure_block
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.deck.render.pptx.shapes import Box
from autooffice.deck.render.pptx.textbox import (
    render_bullets_block,
    render_metric_block,
    render_quote_block,
    render_text_block,
)
from autooffice.design.theme import resolve_theme

THEMES = ("indigo", "hitam")
KPI_SPAN_THREE_WIDTH = 2_522_220
LONG_QUOTE = (
    "Rapat yang baik berakhir dengan keputusan yang jelas, pemilik yang "
    "eksplisit, tenggat yang terukur, dan catatan yang dapat ditindaklanjuti "
    "oleh seluruh peserta pada hari berikutnya."
)
LONG_METRIC_VALUE = "1.248 dari 1.350 target"
LONG_METRIC_LABEL = "Pengguna aktif mingguan dari seluruh unit kerja"


def _rgb(color: str) -> RGBColor:
    return RGBColor.from_string(color[1:])


@pytest.mark.parametrize("theme_name", THEMES)
def test_metric_card_height_matches_measure(theme_name: str) -> None:
    theme = resolve_theme(theme_name)
    block = BlockIR(
        "m1",
        "metric",
        None,
        None,
        {"value": LONG_METRIC_VALUE, "label": LONG_METRIC_LABEL},
    )
    measurement = measure_block(block, width_emu=KPI_SPAN_THREE_WIDTH, theme=theme)
    box = Box(
        left=914_400,
        top=1_000_000,
        width=KPI_SPAN_THREE_WIDTH,
        height=measurement.height_emu,
    )

    card, value, label = render_metric_block(new_slide(), block, box, theme, slide_id="s01")

    padding = theme.card.padding_emu
    assert measurement.line_count > 2
    assert card.top == box.top
    assert card.left == box.left
    assert card.width == box.width
    assert card.height == measurement.height_emu
    assert value.left == box.left + padding
    assert value.width == box.width - 2 * padding
    assert value.top == box.top + padding
    assert value.height + label.height == measurement.height_emu - 2 * padding
    assert label.top + label.height == box.bottom - padding


@pytest.mark.parametrize("theme_name", THEMES)
def test_quote_card_height_matches_measure(theme_name: str) -> None:
    theme = resolve_theme(theme_name)
    block = BlockIR(
        "q1",
        "quote",
        None,
        None,
        {"text": LONG_QUOTE, "attribution": "Catatan tim AutoOffice"},
    )
    measurement = measure_block(block, width_emu=4_000_000, theme=theme)
    box = Box(left=200_000, top=500_000, width=4_000_000, height=measurement.height_emu)

    card, text, attribution = render_quote_block(new_slide(), block, box, theme, slide_id="s01")

    padding = theme.card.padding_emu
    assert measurement.line_count > 3
    assert card.top == box.top
    assert card.height == measurement.height_emu
    assert text.left == box.left + padding
    assert text.width == box.width - 2 * padding
    assert text.top == box.top + padding
    assert text.height + attribution.height == measurement.height_emu - 2 * padding
    assert attribution.top + attribution.height == box.bottom - padding


def test_quote_card_without_attribution_fills_inner_height() -> None:
    theme = resolve_theme("indigo")
    block = BlockIR("q1", "quote", None, None, {"text": LONG_QUOTE})
    measurement = measure_block(block, width_emu=4_000_000, theme=theme)
    box = Box(left=0, top=0, width=4_000_000, height=measurement.height_emu)

    _, text = render_quote_block(new_slide(), block, box, theme, slide_id="s01")

    padding = theme.card.padding_emu
    assert text.height == measurement.height_emu - 2 * padding
    assert text.top + text.height == box.bottom - padding


@pytest.mark.parametrize("theme_name", THEMES)
def test_metric_card_is_fill_only_without_line_or_shadow(theme_name: str) -> None:
    theme = resolve_theme(theme_name)
    block = BlockIR("m1", "metric", None, None, {"value": "95%", "label": "Coverage"})
    box = Box(left=0, top=0, width=2_522_220, height=1_800_000)

    card = render_metric_block(new_slide(), block, box, theme, slide_id="s01")[0]

    sp_pr = card._element.spPr
    effect = sp_pr.find(qn("a:effectLst"))
    assert card.fill.fore_color.rgb == _rgb(theme.card.fill)
    assert card.line.fill.type == MSO_FILL.BACKGROUND
    assert card.shadow.inherit is False
    assert effect is not None
    assert len(effect) == 0
    assert card.adjustments[0] == pytest.approx(theme.card.radius_emu / min(box.width, box.height))


def test_card_padding_is_the_token_value() -> None:
    theme = resolve_theme("indigo")

    assert theme.card.padding_emu == 228600
    assert theme.card.radius_emu == 91440


@pytest.mark.parametrize(
    ("block", "renderer"),
    [
        (BlockIR("t1", "text", None, "body", {"text": "Prosa"}), render_text_block),
        (
            BlockIR("b1", "bullets", None, None, {"items": ("Satu", "Dua")}),
            render_bullets_block,
        ),
    ],
)
def test_text_and_bullets_do_not_gain_a_card(block: BlockIR, renderer) -> None:
    theme = resolve_theme("indigo")
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = renderer(new_slide(), block, box, theme, slide_id="s01")

    assert all(not shape.name.startswith("chrome:card:") for shape in shapes)

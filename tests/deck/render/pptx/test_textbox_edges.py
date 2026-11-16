"""Tes cabang edge text box, block teks, dan bullet numbering."""

from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import pytest
from _edge_helpers import line_spacing_points, new_slide
from pptx.oxml.ns import qn

import autooffice.deck.render.pptx.textbox as textbox_module
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.deck.render.pptx.shapes import (
    Box,
    PptxRenderError,
    collect_render_warnings,
    key_from_shape,
)
from autooffice.deck.render.pptx.textbox import (
    add_keyed_text,
    body_style,
    render_bullets_block,
    render_code_block,
    render_metric_block,
    render_quote_block,
    render_text_block,
    role_style,
)


def _padding(theme) -> int:
    return theme.spacing.card_padding_emu


def _tight_box() -> Box:
    """Kotak teks tanpa inset yang hanya menyisakan tinggi 1 EMU."""
    return Box(left=0, top=0, width=1_000_000, height=1)


def _tight_card_box(theme) -> Box:
    """Kotak card yang hanya menyisakan tinggi 1 EMU setelah padding."""
    padding = theme.card.padding_emu
    return Box(left=0, top=0, width=1_000_000, height=padding * 2 + 1)


def _tight_code_box(theme) -> Box:
    """Kotak code yang menyisakan tinggi 1 EMU setelah padding kartu."""
    padding = _padding(theme)
    return Box(left=0, top=0, width=padding * 4, height=padding * 2 + 1)


def test_add_keyed_text_requires_text_frame(theme) -> None:
    class FakeShapes:
        def add_textbox(self, *args: object) -> SimpleNamespace:
            return SimpleNamespace(has_text_frame=False)

    fake_slide = SimpleNamespace(shapes=FakeShapes())

    with pytest.raises(PptxRenderError, match="tidak memiliki text frame"):
        add_keyed_text(
            fake_slide,
            Box(left=0, top=0, width=1000, height=1000),
            key="s01.title.text",
            text="Judul",
            style=role_style(theme, "body"),
            theme=theme,
        )


def test_render_text_block_rejects_no_body_space_after_heading(theme) -> None:
    block = BlockIR("b1", "text", None, "body", {"heading": "Judul", "text": "Isi"})

    with pytest.raises(PptxRenderError, match="tidak menyisakan ruang untuk teks"):
        render_text_block(new_slide(), block, _tight_box(), theme, slide_id="s01")


def test_render_text_block_collects_font_weight_fallback_warning(theme) -> None:
    block = BlockIR("b1", "text", None, "display", {"text": "Judul"})
    fallback_theme = replace(theme, typography=replace(theme.typography, family="Inter"))
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    with collect_render_warnings() as warnings:
        render_text_block(new_slide(), block, box, fallback_theme, slide_id="s01")

    assert any("font-weight" in warning for warning in warnings)


def test_render_bullets_block_rejects_zero_available_width(theme) -> None:
    block = BlockIR("b1", "bullets", None, None, {"items": ("Satu",)})
    indent = theme.spacing.card_padding_emu
    box = Box(left=0, top=0, width=indent, height=indent * 4)

    with pytest.raises(PptxRenderError, match="tidak memiliki lebar untuk bullets"):
        render_bullets_block(new_slide(), block, box, theme, slide_id="s01")


def test_render_bullets_block_rejects_empty_items(theme) -> None:
    block = BlockIR("b1", "bullets", None, None, {"items": ()})
    box = Box(left=0, top=0, width=1_000_000, height=1_000_000)

    with pytest.raises(PptxRenderError, match="tidak memiliki item"):
        render_bullets_block(new_slide(), block, box, theme, slide_id="s01")


def test_render_bullets_block_rejects_overflow_without_shrinking(theme) -> None:
    block = BlockIR("b1", "bullets", None, None, {"items": ("x" * 200, "y" * 200)})
    indent = theme.spacing.card_padding_emu
    box = Box(left=0, top=0, width=indent + 1, height=2)

    with pytest.raises(PptxRenderError, match="melebihi kotak"):
        render_bullets_block(new_slide(), block, box, theme, slide_id="s01")


def test_render_bullets_block_keeps_all_shapes_inside_box(theme) -> None:
    block = BlockIR("b1", "bullets", None, None, {"items": ("Satu", "Dua")})
    box = Box(left=100, top=200, width=4_000_000, height=3_000_000)

    shapes = render_bullets_block(new_slide(), block, box, theme, slide_id="s01")

    assert len(shapes) == 2
    for shape in shapes:
        assert shape.left >= box.left
        assert shape.top >= box.top
        assert shape.left + shape.width <= box.right
        assert shape.top + shape.height <= box.bottom


def test_render_bullets_block_writes_ordered_numbering(theme) -> None:
    block = BlockIR("b1", "bullets", None, None, {"items": ("Satu", "Dua"), "ordered": True})
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_bullets_block(new_slide(), block, box, theme, slide_id="s01")

    starts = []
    for shape in shapes:
        paragraph = shape.text_frame.paragraphs[0]
        numbering = paragraph._p.find(".//" + qn("a:buAutoNum"))
        assert numbering is not None
        assert numbering.get("type") == "arabicPeriod"
        starts.append(numbering.get("startAt"))
    assert starts == ["1", "2"]


def test_render_quote_block_without_attribution_returns_card_and_text(theme) -> None:
    block = BlockIR("q1", "quote", None, None, {"text": "Kutipan"})
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_quote_block(new_slide(), block, box, theme, slide_id="s01")

    assert len(shapes) == 2
    assert shapes[0].name == "chrome:card:s01.q1"
    assert shapes[1].text_frame.text == "Kutipan"


def test_render_quote_block_rejects_attribution_without_space(theme) -> None:
    block = BlockIR(
        "q1",
        "quote",
        None,
        None,
        {"text": "Kutipan yang panjang", "attribution": "Tim"},
    )

    with pytest.raises(PptxRenderError, match="tidak menyisakan ruang untuk attribution"):
        render_quote_block(new_slide(), block, _tight_card_box(theme), theme, slide_id="s01")


def test_render_metric_block_returns_card_value_and_label(theme) -> None:
    block = BlockIR("m1", "metric", None, None, {"label": "Coverage", "value": "95%"})
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_metric_block(new_slide(), block, box, theme, slide_id="s01")

    assert len(shapes) == 3
    assert shapes[0].name == "chrome:card:s01.m1"
    assert [shape.text_frame.text for shape in shapes[1:]] == ["95%", "Coverage"]


def test_render_metric_block_rejects_overflow_without_shrinking(theme) -> None:
    block = BlockIR("m1", "metric", None, None, {"label": "Coverage", "value": "95%"})

    with pytest.raises(PptxRenderError, match="melebihi kotak"):
        render_metric_block(new_slide(), block, _tight_card_box(theme), theme, slide_id="s01")


def test_render_metric_block_keeps_measured_heights_when_exact(theme) -> None:
    block = BlockIR("m1", "metric", None, None, {"label": "Coverage", "value": "95%"})
    roomy = Box(left=0, top=0, width=4_000_000, height=3_000_000)
    natural = render_metric_block(new_slide(), block, roomy, theme, slide_id="s01")
    natural_heights = [shape.height for shape in natural[1:]]

    padding = theme.card.padding_emu
    exact = Box(
        left=0,
        top=0,
        width=4_000_000,
        height=sum(natural_heights) + 2 * padding,
    )
    shapes = render_metric_block(new_slide(), block, exact, theme, slide_id="s01")

    assert [shape.height for shape in shapes[1:]] == natural_heights
    assert sum(shape.height for shape in shapes[1:]) == exact.height - 2 * padding
    assert shapes[-1].top + shapes[-1].height == exact.bottom - padding


@pytest.mark.parametrize("status", ["success", "warning", "danger"])
def test_render_metric_block_applies_status_color(theme, status: str) -> None:
    block = BlockIR(
        "m1",
        "metric",
        None,
        None,
        {"label": "Coverage", "value": "95%", "status": status},
    )
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_metric_block(new_slide(), block, box, theme, slide_id="s01")

    value_run = shapes[1].text_frame.paragraphs[0].runs[0]
    assert value_run.font.color.rgb == _rgb(theme.colors.status[status])


def test_render_metric_block_treats_neutral_as_ink(theme) -> None:
    block = BlockIR(
        "m1",
        "metric",
        None,
        None,
        {"label": "Coverage", "value": "95%", "status": "neutral"},
    )
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_metric_block(new_slide(), block, box, theme, slide_id="s01")

    value_run = shapes[1].text_frame.paragraphs[0].runs[0]
    assert value_run.font.color.rgb == _rgb(theme.colors.ink)


def test_render_code_block_without_filename_returns_card_and_code(theme) -> None:
    block = BlockIR("c1", "code", None, None, {"code": "print(1)", "line_numbers": False})
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_code_block(new_slide(), block, box, theme, slide_id="s01")
    names = {shape.name: shape for shape in shapes}

    assert len(shapes) == 2
    assert "chrome:code-card:s01.c1" in names
    assert names["autooffice:key:s01.c1.code"].text_frame.text == "print(1)"


def test_render_code_block_renders_line_numbers_as_chrome(theme) -> None:
    block = BlockIR("c1", "code", None, None, {"code": "print(1)\nprint(2)"})
    box = Box(left=100, top=200, width=4_000_000, height=3_000_000)

    shapes = render_code_block(new_slide(), block, box, theme, slide_id="s01")
    inner = box.inset(_padding(theme))
    names = {shape.name: shape for shape in shapes}

    numbers = names["chrome:code-lines:s01.c1"]
    code = names["autooffice:key:s01.c1.code"]
    assert key_from_shape(numbers) is None
    assert numbers.text_frame.text == "1\n2"
    assert code.text_frame.text == "print(1)\nprint(2)"
    assert numbers.left == inner.left
    assert numbers.left + numbers.width <= code.left
    assert code.left + code.width <= inner.right
    for paragraph in numbers.text_frame.paragraphs:
        assert line_spacing_points(paragraph) == round(
            theme.code.size_pt * theme.code.line_height * 100
        )


def test_render_code_block_rejects_no_room_after_filename(theme) -> None:
    block = BlockIR("c1", "code", None, None, {"code": "print(1)", "filename": "kode.py"})

    with pytest.raises(PptxRenderError, match="tidak memiliki ruang teks"):
        render_code_block(new_slide(), block, _tight_code_box(theme), theme, slide_id="s01")


@pytest.mark.parametrize(
    ("role", "expected"),
    [("label", "ink_secondary"), ("kicker", "accent")],
)
def test_role_style_maps_secondary_and_accent_roles(theme, role: str, expected: str) -> None:
    assert role_style(theme, role).color == getattr(theme.colors, expected)


@pytest.mark.parametrize(
    ("role", "size_pt", "weight", "tracking"),
    [
        ("display", 44.0, 800, -0.01),
        ("title", 30.0, 700, -0.01),
        ("lead", 18.0, 600, -0.01),
        ("body", 16.5, 400, -0.01),
        ("caption", 12.5, 400, -0.01),
        ("label", 14.0, 600, -0.01),
        ("kicker", 12.5, 700, 0.08),
    ],
)
def test_role_style_uses_typography_tiers(
    theme,
    role: str,
    size_pt: float,
    weight: int,
    tracking: float,
) -> None:
    style = role_style(theme, role)

    assert style.size_pt == size_pt
    assert style.weight == weight
    assert style.tracking_em == tracking


def test_bullets_use_hanging_indent_and_item_gap(theme) -> None:
    block = BlockIR("b1", "bullets", None, None, {"items": ("Satu", "Dua")})
    box = Box(left=100, top=200, width=4_000_000, height=3_000_000)

    shapes = render_bullets_block(new_slide(), block, box, theme, slide_id="s01")

    for shape in shapes:
        p_pr = shape.text_frame.paragraphs[0]._p.get_or_add_pPr()
        assert p_pr.get("marL") == str(theme.spacing.card_padding_emu)
        assert p_pr.get("indent") == str(-theme.spacing.card_padding_emu)
    assert shapes[1].top - (shapes[0].top + shapes[0].height) == theme.spacing.sm_emu


def test_body_style_default_weight_comes_from_weights_zero(theme) -> None:
    custom = replace(
        theme,
        typography=replace(theme.typography, weights=(500, 600, 700, 800)),
    )

    assert body_style(custom).weight == 500


def test_bullets_use_body_weight_from_theme(theme, monkeypatch: pytest.MonkeyPatch) -> None:
    custom = replace(
        theme,
        typography=replace(theme.typography, weights=(500, 600, 700, 800)),
    )
    captured: list[int] = []

    def fake_apply_run_style(_run: object, **kwargs: object) -> None:
        captured.append(cast("int", kwargs["weight"]))

    monkeypatch.setattr(textbox_module, "apply_run_style", fake_apply_run_style)
    block = BlockIR("b1", "bullets", None, None, {"items": ("Satu", "Dua")})
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    render_bullets_block(new_slide(), block, box, custom, slide_id="s01")

    assert captured == [500, 500]


def test_metric_without_status_uses_ink(theme) -> None:
    block = BlockIR("m1", "metric", None, None, {"label": "Coverage", "value": "95%"})
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_metric_block(new_slide(), block, box, theme, slide_id="s01")

    value_run = shapes[1].text_frame.paragraphs[0].runs[0]
    assert value_run.font.color.rgb == _rgb(theme.colors.ink)


def test_metric_label_uses_label_token(theme) -> None:
    block = BlockIR("m1", "metric", None, None, {"label": "Coverage", "value": "95%"})
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_metric_block(new_slide(), block, box, theme, slide_id="s01")

    label_run = shapes[2].text_frame.paragraphs[0].runs[0]
    assert label_run.font.size is not None
    assert label_run.font.size.pt == theme.typography.label_pt


def test_code_card_geometry_filename_and_line_numbers(theme) -> None:
    block = BlockIR(
        "c1",
        "code",
        None,
        None,
        {"code": "print(1)\nprint(2)", "filename": "kode.py"},
    )
    box = Box(left=100, top=200, width=4_000_000, height=3_000_000)

    shapes = render_code_block(new_slide(), block, box, theme, slide_id="s01")
    names = {shape.name: shape for shape in shapes}
    card = names["chrome:code-card:s01.c1"]
    filename = names["autooffice:key:s01.c1.filename"]
    code = names["autooffice:key:s01.c1.code"]
    numbers = names["chrome:code-lines:s01.c1"]

    assert card.fill.fore_color.rgb == _rgb(theme.colors.surface)
    assert card.line.color.rgb == _rgb(theme.colors.border)
    assert card.adjustments[0] > 0
    filename_run = filename.text_frame.paragraphs[0].runs[0]
    code_run = code.text_frame.paragraphs[0].runs[0]
    number_run = numbers.text_frame.paragraphs[0].runs[0]
    assert filename_run.font.size is not None
    assert filename_run.font.size.pt == theme.code.filename_pt
    assert filename_run.font.bold is True
    assert code_run.font.size is not None
    assert code_run.font.size.pt == theme.code.size_pt
    assert number_run.font.color.rgb == _rgb(theme.colors.muted)
    assert code.top == filename.top + filename.height + theme.spacing.sm_emu


def _rgb(color: str) -> object:
    from pptx.dml.color import RGBColor

    return RGBColor.from_string(color[1:])

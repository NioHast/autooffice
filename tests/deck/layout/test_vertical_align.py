"""Test komposisi vertikal: default top, center konten, dan section opener."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from autooffice.deck.layout.custom import (
    CUSTOM_VERTICAL_ALIGN,
    CustomLayoutError,
    plan_custom_slide,
    plan_custom_slide_with_findings,
)
from autooffice.deck.layout.grid import Grid
from autooffice.deck.layout.overflow import plan_deck, plan_slide
from autooffice.deck.layout.presets import cover as cover_preset
from autooffice.deck.layout.presets import section as section_preset
from autooffice.deck.layout.registry import layout_registry
from autooffice.deck.layout.spec import (
    LayoutSpec,
    LayoutSpecError,
    SlideLayout,
    is_header_row,
    vertical_alignment_shifts,
)
from autooffice.deck.model.deck_ir import BlockIR, DeckIR, SlideIR

CENTERED_PRESETS = (
    "background",
    "bars",
    "closing",
    "code",
    "comparison",
    "content",
    "cover",
    "diagram",
    "donut",
    "flow",
    "image-full",
    "image-grid",
    "image-split",
    "kpi",
    "line",
    "matrix",
    "section",
    "table",
    "toc",
)


def _body_slide(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    *,
    with_note: bool = False,
) -> SlideIR:
    blocks = [
        block_factory("title", "text", fields={"text": "Judul"}, role="title"),
        block_factory("body", "text", fields={"text": "Isi singkat"}, role="body"),
    ]
    if with_note:
        blocks.append(block_factory("note", "text", fields={"text": "Catatan"}, role="caption"))
    return slide_factory(tuple(blocks))


def _stack_bottom(layout: SlideLayout) -> int:
    return max(box.top_emu + box.height_emu for box in layout.boxes)


def _cover_slide(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    *,
    with_role: bool,
) -> SlideIR:
    blocks = [
        block_factory("kicker", "text", fields={"text": "Demo"}, role="kicker"),
        block_factory("title", "text", fields={"text": "Judul"}, role="title"),
        block_factory("subtitle", "text", fields={"text": "Subjudul"}, role="lead"),
        block_factory("author", "text", fields={"text": "Tim"}, role="label"),
    ]
    if with_role:
        blocks.append(block_factory("role", "text", fields={"text": "Peran"}, role="caption"))
    blocks.append(
        block_factory(
            "summary",
            "metric",
            fields={"label": "Block", "value": "11"},
        )
    )
    return slide_factory(tuple(blocks), layout="cover")


def _chart_slide(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    *,
    layout_id: str,
    kind: str,
) -> SlideIR:
    blocks = [
        block_factory("title", "text", fields={"text": "Judul"}, role="title"),
        block_factory("lead", "text", fields={"text": "Lead"}, role="lead"),
        block_factory(
            "chart1",
            "chart",
            fields={"kind": kind},
        ),
    ]
    if layout_id == "donut":
        blocks.append(
            block_factory(
                "legend",
                "bullets",
                fields={"items": ["Satu", "Dua", "Tiga", "Empat"]},
            )
        )
    blocks.append(block_factory("note", "text", fields={"text": "Catatan"}, role="caption"))
    return slide_factory(tuple(blocks), layout=layout_id)


def test_layout_spec_defaults_to_top(demo_spec: LayoutSpec) -> None:
    assert demo_spec.vertical_align == "top"


def test_layout_spec_rejects_unknown_vertical_align(demo_spec: LayoutSpec) -> None:
    with pytest.raises(LayoutSpecError, match="vertical_align"):
        replace(demo_spec, vertical_align="middle")  # type: ignore[arg-type]


def test_all_presets_use_centered_vertical_align() -> None:
    registry = layout_registry()

    assert set(registry) == set(CENTERED_PRESETS)
    assert all(registry[layout_id].vertical_align == "center" for layout_id in CENTERED_PRESETS)


@pytest.mark.parametrize(
    ("roles", "expected"),
    (
        (("title",), True),
        (("label", "caption"), True),
        (("title", "caption"), True),
        (("caption",), False),
        (("title", "body"), False),
        (("body", "caption"), False),
        ((None,), False),
        ((), False),
    ),
)
def test_header_row_classification_is_per_slot(
    roles: tuple[str | None, ...],
    expected: bool,
) -> None:
    assert is_header_row(roles) is expected


def test_vertical_shifts_reject_mismatched_lengths() -> None:
    with pytest.raises(LayoutSpecError, match="tidak sama"):
        vertical_alignment_shifts(
            (100,),
            (),
            content_bottom_emu=500,
            vertical_align="center",
        )


def test_vertical_shifts_pin_leading_headers() -> None:
    assert vertical_alignment_shifts(
        (100, 200, 300),
        (True, False, False),
        content_bottom_emu=500,
        vertical_align="center",
    ) == (0, 100, 100)


def test_vertical_shifts_center_an_all_header_stack() -> None:
    assert vertical_alignment_shifts(
        (100, 200, 300),
        (True, True, True),
        content_bottom_emu=500,
        vertical_align="center",
    ) == (100, 100, 100)


def test_vertical_shifts_do_not_move_an_overflowing_stack() -> None:
    assert vertical_alignment_shifts(
        (100, 600),
        (True, False),
        content_bottom_emu=500,
        vertical_align="center",
    ) == (0, 0)


def test_top_alignment_keeps_first_row_at_content_top(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
    theme,
    grid: Grid,
) -> None:
    layout = plan_slide(_body_slide(block_factory, slide_factory), demo_spec, theme)
    title_box = layout.boxes[0]

    assert title_box.top_emu == grid.content_top_emu


def test_centered_layout_pins_title_and_centers_content(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
    theme,
    grid: Grid,
) -> None:
    slide = _body_slide(block_factory, slide_factory, with_note=True)
    top_layout = plan_slide(slide, demo_spec, theme)
    centered_layout = plan_slide(
        slide,
        replace(demo_spec, vertical_align="center"),
        theme,
    )
    shift = (grid.content_bottom_emu - _stack_bottom(top_layout)) // 2
    top_title, top_body, top_note = top_layout.boxes
    title_box, body_box, note_box = centered_layout.boxes

    assert shift > 0
    assert title_box.top_emu == top_title.top_emu == grid.content_top_emu
    assert body_box.top_emu == top_body.top_emu + shift
    assert note_box.top_emu == top_note.top_emu + shift
    assert body_box.top_emu == note_box.top_emu
    assert _stack_bottom(centered_layout) <= grid.content_bottom_emu
    assert centered_layout.overflow_keys == ()


def test_centered_section_layout_centers_the_whole_stack(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
    grid: Grid,
) -> None:
    blocks = (
        block_factory("number", "text", fields={"text": "01"}, role="display"),
        block_factory("title", "text", fields={"text": "Bagian"}, role="title"),
        block_factory("subtitle", "text", fields={"text": "Pembuka"}, role="lead"),
    )
    slide = slide_factory(blocks, layout="section")
    top_layout = plan_slide(
        slide,
        replace(section_preset.LAYOUT, vertical_align="top"),
        theme,
    )
    centered_layout = plan_slide(slide, section_preset.LAYOUT, theme)
    shift = (grid.content_bottom_emu - _stack_bottom(top_layout)) // 2

    assert shift > 0
    assert tuple(box.top_emu for box in centered_layout.boxes) == tuple(
        box.top_emu + shift for box in top_layout.boxes
    )
    assert centered_layout.boxes[0].top_emu == grid.content_top_emu + shift
    assert _stack_bottom(centered_layout) <= grid.content_bottom_emu


def test_cover_mixed_header_row_stays_pinned_when_optional_caption_present(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
    grid: Grid,
) -> None:
    variants = {}
    for with_role in (False, True):
        slide = _cover_slide(block_factory, slide_factory, with_role=with_role)
        top_layout = plan_slide(slide, replace(cover_preset.LAYOUT, vertical_align="top"), theme)
        centered_layout = plan_slide(slide, cover_preset.LAYOUT, theme)
        variants[with_role] = (
            {box.block_id: box for box in top_layout.boxes},
            {box.block_id: box for box in centered_layout.boxes},
            (grid.content_bottom_emu - _stack_bottom(top_layout)) // 2,
        )

    without_top, without_center, without_shift = variants[False]
    with_top, with_center, with_shift = variants[True]

    assert without_shift > 0
    assert with_shift > 0
    assert with_center["author"].top_emu == without_center["author"].top_emu
    assert with_center["author"].top_emu == without_top["author"].top_emu
    assert with_center["role"].top_emu == with_center["author"].top_emu
    assert with_center["summary"].top_emu == with_top["summary"].top_emu + with_shift
    assert without_center["summary"].top_emu == without_top["summary"].top_emu + without_shift


@pytest.mark.parametrize(
    ("layout_id", "kind"),
    (("bars", "bar"), ("line", "line"), ("donut", "donut")),
)
def test_chart_presets_center_rows_without_shrinking_media(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
    grid: Grid,
    layout_id: str,
    kind: str,
) -> None:
    spec = layout_registry()[layout_id]
    slide = _chart_slide(
        block_factory,
        slide_factory,
        layout_id=layout_id,
        kind=kind,
    )
    top_layout = plan_slide(slide, replace(spec, vertical_align="top"), theme)
    centered_layout = plan_slide(slide, spec, theme)
    slack_before = grid.content_bottom_emu - _stack_bottom(top_layout)
    slack_after = grid.content_bottom_emu - _stack_bottom(centered_layout)
    shift = slack_before // 2
    top_boxes = {box.block_id: box for box in top_layout.boxes}
    centered_boxes = {box.block_id: box for box in centered_layout.boxes}

    assert slack_before > 500_000
    assert shift > 0
    assert slack_after == slack_before - shift
    assert centered_boxes["title"].top_emu == top_boxes["title"].top_emu
    assert centered_boxes["chart1"].top_emu == top_boxes["chart1"].top_emu + shift
    assert centered_boxes["chart1"].height_emu == top_boxes["chart1"].height_emu
    assert centered_boxes["chart1"].width_emu == top_boxes["chart1"].width_emu
    assert all(box.top_emu >= grid.content_top_emu for box in centered_layout.boxes)
    assert _stack_bottom(centered_layout) <= grid.content_bottom_emu
    assert centered_layout.overflow_keys == top_layout.overflow_keys == ()


def test_centered_layout_preserves_overflow_semantics(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
    theme,
) -> None:
    slide = slide_factory(
        (
            block_factory("title", "text", fields={"text": "Judul"}, role="title"),
            block_factory(
                "body",
                "text",
                fields={"text": "\n".join(["baris"] * 1_000)},
                role="body",
            ),
        )
    )
    top_layout = plan_slide(slide, demo_spec, theme)
    centered_layout = plan_slide(
        slide,
        replace(demo_spec, vertical_align="center"),
        theme,
    )

    assert centered_layout.boxes == top_layout.boxes
    assert centered_layout.overflow_keys == top_layout.overflow_keys
    assert centered_layout.overflow_keys


def test_custom_planner_defaults_to_top_and_centers_on_request(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
    grid: Grid,
) -> None:
    title = block_factory("title", "text", fields={"text": "Judul"}, role="title", span=12)
    body = block_factory("body", "text", fields={"text": "Isi"}, role="body", span=12)
    rows = ((title,), (body,))
    slide = slide_factory((title, body), layout="custom")
    top_layout = plan_custom_slide(slide, theme, rows=rows)
    centered_layout = plan_custom_slide(slide, theme, rows=rows, vertical_align="center")
    shift = (grid.content_bottom_emu - _stack_bottom(top_layout)) // 2
    top_title, top_body = top_layout.boxes
    title_box, body_box = centered_layout.boxes

    assert shift > 0
    assert title_box.top_emu == top_title.top_emu
    assert top_body.top_emu == top_title.top_emu + top_title.height_emu + grid.row_gap_emu
    assert body_box.top_emu == top_body.top_emu + shift
    assert _stack_bottom(centered_layout) <= grid.content_bottom_emu


def test_custom_text_without_title_role_is_content(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
    grid: Grid,
) -> None:
    unroled_title = block_factory(
        "title",
        "text",
        fields={"text": "Judul tanpa role"},
        span=12,
    )
    body = block_factory("body", "text", fields={"text": "Isi"}, role="body", span=12)
    unroled_slide = slide_factory((unroled_title, body), layout="custom")
    unroled_top = plan_custom_slide(
        unroled_slide,
        theme,
        rows=((unroled_title,), (body,)),
    )
    unroled_centered = plan_custom_slide(
        unroled_slide,
        theme,
        rows=((unroled_title,), (body,)),
        vertical_align="center",
    )
    shift = (grid.content_bottom_emu - _stack_bottom(unroled_top)) // 2

    assert shift > 0
    assert unroled_centered.boxes[0].top_emu == unroled_top.boxes[0].top_emu + shift
    assert unroled_centered.boxes[0].top_emu > grid.content_top_emu

    titled = block_factory("title", "text", fields={"text": "Judul"}, role="title", span=12)
    titled_slide = slide_factory((titled, body), layout="custom")
    titled_centered = plan_custom_slide(
        titled_slide,
        theme,
        rows=((titled,), (body,)),
        vertical_align="center",
    )

    assert titled_centered.boxes[0].top_emu == grid.content_top_emu


def test_deck_planning_uses_centered_custom_policy(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme,
) -> None:
    title = block_factory("title", "text", fields={"text": "Judul"}, role="title", span=12)
    body = block_factory("body", "text", fields={"text": "Isi"}, role="body", span=12)
    slide = slide_factory(
        (title, body),
        layout="custom",
        rows=(("title",), ("body",)),
    )
    plan = plan_deck(deck_factory((slide,)), theme, layouts={})
    centered = plan_custom_slide_with_findings(
        slide,
        theme,
        vertical_align=CUSTOM_VERTICAL_ALIGN,
    ).layout

    assert CUSTOM_VERTICAL_ALIGN == "center"
    assert plan.slides[0] == centered


def test_custom_planner_rejects_unknown_vertical_align(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
) -> None:
    body = block_factory("body", "text", fields={"text": "Isi"}, role="body", span=12)
    slide = slide_factory((body,), layout="custom")

    with pytest.raises(CustomLayoutError, match="vertical_align"):
        plan_custom_slide_with_findings(
            slide,
            theme,
            rows=((body,),),
            vertical_align="middle",  # type: ignore[arg-type]
        )

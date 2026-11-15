"""Tes coverage nyata dari shape, table cell, notes, dan alt text."""

from collections import Counter
from types import SimpleNamespace
from typing import Self

import pytest
from lxml import etree
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Emu

from autooffice.deck.model.deck_ir import (
    BlockIR,
    DeckIR,
    KeyBinding,
    KeyManifest,
    SlideIR,
)
from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.pptx.coverage import (
    CoverageError,
    _check_alt,
    _check_notes,
    _Scan,
    _scan_slide,
    collect_coverage,
)
from autooffice.deck.render.pptx.shapes import KEY_MARKER, set_keyed_shape
from autooffice.deck.render.protocol import CoverageReport, OutputTarget, RenderRequest


def _deck(*, keys: tuple[KeyBinding, ...]) -> DeckIR:
    block = BlockIR("title", "text", None, "title", {"text": "Judul"})
    return DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Coverage Deck", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "content", 0, (block,), None, None),),
        keys=KeyManifest(keys),
    )


def _key(key: str) -> KeyBinding:
    return KeyBinding(
        key=key,
        slide_id="s01",
        block_id="title",
        leaf="text",
        kind="text",
        sync=True,
        yaml_path=("slides", 0, "blocks", 0, "text"),
        value="nilai",
        plain_text="nilai",
    )


def _blank_presentation() -> Presentation:
    presentation = Presentation()
    presentation.slides.add_slide(presentation.slide_layouts[6])
    return presentation


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


def test_missing_declared_key_is_reported() -> None:
    report = collect_coverage(_blank_presentation(), _deck(keys=(_key("s01.title.text"),)))

    assert report.ok is False
    assert report.missing_keys == ("s01.title.text",)


def test_duplicate_rendered_key_is_reported() -> None:
    presentation = _blank_presentation()
    slide = presentation.slides[0]
    for text in ("Pertama", "Kedua"):
        shape = slide.shapes.add_textbox(Emu(0), Emu(0), Emu(100000), Emu(100000))
        shape.text_frame.text = text
        set_keyed_shape(shape, "s01.title.text", description=text)

    report = collect_coverage(presentation, _deck(keys=(_key("s01.title.text"),)))

    assert report.duplicate_keys == ("s01.title.text",)
    assert report.ok is False


def test_visible_shape_without_key_is_reported() -> None:
    presentation = _blank_presentation()
    shape = presentation.slides[0].shapes.add_textbox(Emu(0), Emu(0), Emu(100000), Emu(100000))
    shape.text_frame.text = "Teks tanpa key"

    report = collect_coverage(presentation, _deck(keys=()))

    assert report.unkeyed_visible[0].startswith("s01:")
    assert report.ok is False


def test_missing_manifest_render_fails_without_final_artifact(
    missing_manifest_case,
    theme,
) -> None:
    with pytest.raises(CoverageError) as error:
        _render(missing_manifest_case, theme)

    assert "s01.title.text" in error.value.report.unkeyed_visible
    assert not (missing_manifest_case.workspace / "missing-manifest.pptx").exists()


def test_missing_image_alt_fails_render(
    missing_alt_case,
    theme,
) -> None:
    with pytest.raises(CoverageError) as error:
        _render(missing_alt_case, theme)

    assert error.value.report.missing_alt == ("s01.image1",)
    assert not (missing_alt_case.workspace / "missing-alt.pptx").exists()


def test_notes_text_is_counted_as_key() -> None:
    presentation = _blank_presentation()
    presentation.slides[0].notes_slide.notes_text_frame.text = "Catatan"
    notes_key = KeyBinding(
        key="s01.notes",
        slide_id="s01",
        block_id=None,
        leaf="notes",
        kind="notes",
        sync=True,
        yaml_path=("slides", 0, "notes"),
        value="Catatan",
        plain_text="Catatan",
    )
    block = BlockIR("title", "text", None, "title", {"text": "Judul"})
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Notes Deck", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "content", 0, (block,), "Catatan", None),),
        keys=KeyManifest((notes_key, _key("s01.title.text"))),
    )
    shape = presentation.slides[0].shapes.add_textbox(Emu(0), Emu(0), Emu(100), Emu(100))
    shape.text_frame.text = "Judul"
    set_keyed_shape(shape, "s01.title.text", description="Judul")

    report = collect_coverage(presentation, deck)

    assert report.missing_keys == ()
    assert report.ok is True


class _CountingBindings(tuple):
    """Tuple binding yang menghitung setiap kali diiterasi."""

    def __new__(cls, bindings: tuple[KeyBinding, ...]) -> Self:
        instance = super().__new__(cls, bindings)
        instance.iterations = 0
        return instance

    def __iter__(self):
        self.iterations += 1
        return super().__iter__()


def _fake_keyed_shape(key: str) -> SimpleNamespace:
    element = etree.Element(qn("p:sp"))
    node = etree.SubElement(element, qn("p:cNvPr"))
    node.set("name", f"{KEY_MARKER}{key}")
    node.set("title", key)
    node.set("descr", "Teks")
    return SimpleNamespace(
        _element=element,
        has_table=False,
        has_text_frame=True,
        text_frame=SimpleNamespace(text="Teks"),
    )


def _scale_presentation(
    slide_count: int = 300,
) -> tuple[SimpleNamespace, DeckIR, CoverageReport]:
    """Bangun presentasi sintetis dengan 20 key per slide dan temuan yang diketahui."""
    slides: list[SimpleNamespace] = []
    slide_irs: list[SlideIR] = []
    bindings: list[KeyBinding] = []
    missing: list[str] = []
    duplicate: set[str] = set()
    unkeyed: set[str] = set()
    for index in range(slide_count):
        slide_id = f"s{index + 1:03d}"
        keys = [f"{slide_id}.text{position}.text" for position in range(1, 21)]
        shapes = [_fake_keyed_shape(key) for key in keys]
        if (index + 1) % 37 == 0:
            shapes.pop()
            missing.append(keys[-1])
        if (index + 1) % 53 == 0:
            shapes.append(_fake_keyed_shape(keys[0]))
            duplicate.add(keys[0])
        if index > 0 and index % 41 == 0:
            previous_key = f"s{index:03d}.text2.text"
            shapes.append(_fake_keyed_shape(previous_key))
            duplicate.add(previous_key)
            unkeyed.add(f"{slide_id}:{previous_key}")
        extra_key = f"{slide_id}.extra.text"
        shapes.append(_fake_keyed_shape(extra_key))
        unkeyed.add(extra_key)
        slides.append(SimpleNamespace(shapes=tuple(shapes), has_notes_slide=False))
        slide_irs.append(SlideIR(slide_id, "content", index, (), None, None))
        bindings.extend(_scale_binding(key, slide_id) for key in keys)
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Scale Deck", "author": "AutoOffice"},
        theme_name="indigo",
        slides=tuple(slide_irs),
        keys=KeyManifest(_CountingBindings(tuple(bindings))),
    )
    expected = CoverageReport(
        missing_keys=tuple(sorted(missing)),
        duplicate_keys=tuple(sorted(duplicate)),
        unkeyed_visible=tuple(sorted(unkeyed)),
        missing_alt=(),
    )
    return SimpleNamespace(slides=tuple(slides)), deck, expected


def _scale_binding(key: str, slide_id: str) -> KeyBinding:
    return KeyBinding(
        key=key,
        slide_id=slide_id,
        block_id=None,
        leaf="text",
        kind="text",
        sync=True,
        yaml_path=(),
        value="nilai",
        plain_text="nilai",
    )


def _reference_report(presentation: SimpleNamespace, deck: DeckIR) -> CoverageReport:
    """Agregasi coverage dengan pencarian per key tanpa indeks."""
    scan = _Scan()
    for slide, slide_ir in zip(presentation.slides, deck.slides, strict=True):
        _scan_slide(slide, slide_ir, scan)
        _check_notes(slide, slide_ir, scan)
        _check_alt(slide, slide_ir, scan)

    bindings = deck.keys.bindings
    declared = tuple(binding.key for binding in bindings)
    declared_set = set(declared)
    rendered = [key for keys in scan.keys_by_slide.values() for key in keys]
    rendered_set = set(rendered)
    counts = Counter(rendered)
    declared_counts = Counter(declared)
    duplicate = {key for key, count in counts.items() if count > 1} | {
        key for key, count in declared_counts.items() if count > 1
    }
    missing = sorted(
        {
            binding.key
            for binding in bindings
            if binding.key not in set(scan.keys_by_slide.get(binding.slide_id, ()))
        }
    )
    unkeyed = list(scan.unkeyed)
    unkeyed.extend(sorted(rendered_set - declared_set))
    for key in sorted(rendered_set & declared_set):
        expected_slides = {binding.slide_id for binding in bindings if binding.key == key}
        actual_slides = {slide_id for slide_id, keys in scan.keys_by_slide.items() if key in keys}
        for slide_id in sorted(actual_slides - expected_slides):
            unkeyed.append(f"{slide_id}:{key}")
    return CoverageReport(
        missing_keys=tuple(missing),
        duplicate_keys=tuple(sorted(duplicate)),
        unkeyed_visible=tuple(sorted(set(unkeyed))),
        missing_alt=tuple(sorted(set(scan.missing_alt))),
    )


def test_scale_renderer_coverage_matches_golden_report() -> None:
    presentation, deck, expected = _scale_presentation()

    report = collect_coverage(presentation, deck)
    iterations = deck.keys.bindings.iterations

    assert len(presentation.slides) == 300
    assert len(deck.keys.bindings) == 6000
    assert report == expected
    assert iterations <= 4
    assert len(report.unkeyed_visible) == 307
    assert len(report.duplicate_keys) == 12
    assert report.ok is False


def test_renderer_coverage_matches_reference_aggregation() -> None:
    presentation, deck, expected = _scale_presentation(slide_count=48)

    report = collect_coverage(presentation, deck)
    reference = _reference_report(presentation, deck)

    assert report == expected
    assert report == reference

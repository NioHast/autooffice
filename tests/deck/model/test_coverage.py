"""Test coverage plan dan deteksi key/alt yang tidak lengkap."""

from pathlib import Path
from typing import Self

from autooffice.deck.model import (
    BlockIR,
    DeckIR,
    KeyBinding,
    KeyManifest,
    SlideIR,
    build_coverage_plan,
    check_coverage,
    compile_deck,
    load_deck,
)
from autooffice.deck.model.coverage import _expected_leaves


def _deck(blocks: tuple[BlockIR, ...]) -> DeckIR:
    return DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Coverage Deck"},
        theme_name="indigo",
        slides=(
            SlideIR(
                slide_id="s01",
                layout="content",
                order=0,
                blocks=blocks,
                notes=None,
            ),
        ),
        keys=KeyManifest(bindings=()),
    )


def _text_block() -> BlockIR:
    return BlockIR(
        block_id="title",
        block_type="text",
        span=None,
        role="title",
        fields={"text": "Judul"},
    )


def _image_block(alt: str) -> BlockIR:
    return BlockIR(
        block_id="image1",
        block_type="image",
        span=None,
        role=None,
        fields={"path": "assets/a.png", "alt": alt, "fit": "contain"},
    )


def test_plan_from_all_blocks_is_complete(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "all-blocks.yaml"))
    plan = build_coverage_plan(deck)

    assert plan.ok is True
    assert len(plan.declared_keys) == 31
    assert plan.unkeyed_visible == ()
    assert plan.missing_alt == ()
    assert plan.charts[0].chart_id == "s01.chart1"


def test_plan_findings_are_ok_for_all_rendered_keys(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "all-blocks.yaml"))
    plan = build_coverage_plan(deck)
    findings = plan.findings(deck.keys.keys())

    assert findings.ok is True
    assert findings.missing == ()
    assert findings.extra == ()
    assert findings.duplicate == ()


def test_missing_extra_and_duplicate_rendered_keys_detected(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "all-blocks.yaml"))
    plan = build_coverage_plan(deck)
    rendered = list(deck.keys.keys())
    missing = rendered.pop(0)
    rendered.append("s01.unknown.text")
    rendered.append(rendered[0])
    findings = plan.findings(rendered)

    assert findings.missing == (missing,)
    assert findings.extra == ("s01.unknown.text",)
    assert findings.duplicate == (rendered[0],)
    assert findings.ok is False


def test_unkeyed_visible_block_detected() -> None:
    plan = build_coverage_plan(_deck((_text_block(),)))

    assert plan.unkeyed_visible == ("s01.title",)
    assert plan.ok is False


def test_defensive_missing_alt_detected() -> None:
    """Guard internal: schema menolak alt kosong sebelum IR sampai ke plan."""
    plan = build_coverage_plan(_deck((_image_block("   "),)))

    assert plan.missing_alt == ("s01.image1",)
    assert plan.ok is False


def test_defensive_duplicate_manifest_key_detected(fixture_dir: Path) -> None:
    """Guard internal: KeyRegistry menolak key duplikat sebelum IR terbentuk."""
    deck = compile_deck(load_deck(fixture_dir / "minimal.yaml"))
    first = deck.keys.bindings[0]
    duplicate_deck = DeckIR(
        schema=deck.schema,
        meta=deck.meta,
        theme_name=deck.theme_name,
        slides=deck.slides,
        keys=KeyManifest(bindings=(first, first)),
    )
    plan = build_coverage_plan(duplicate_deck)

    assert plan.duplicate_keys == (first.key,)
    assert plan.ok is False


def test_check_coverage_convenience(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "minimal.yaml"))

    assert check_coverage(deck, deck.keys.keys()).ok is True


def test_report_is_deterministic_and_has_schema(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "all-blocks.yaml"))
    plan = build_coverage_plan(deck)
    report = plan.to_report(deck.keys.keys())

    assert report["schema"] == "autooffice.coverage/v1"
    assert report["deck_id"] == "semua-block"
    assert report["declared"] == 31
    assert report["rendered"] == 31
    assert report["missing"] == []
    assert report["extra"] == []
    assert report["duplicate"] == []
    assert report["unkeyed_visible"] == []
    assert report["missing_alt"] == []
    assert report["charts"] == [{"chart_id": "s01.chart1", "native": True, "key": "s01.chart1"}]


def test_visible_and_sync_keys_are_separated(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "all-blocks.yaml"))
    plan = build_coverage_plan(deck)

    assert "s01.title.text" in plan.visible_keys
    assert "s01.notes" not in plan.visible_keys
    assert "s01.chart1.series1.value1" in plan.data_keys
    assert "s01.chart1.title" in plan.visible_keys
    assert "s01.chart1.title" not in plan.sync_keys
    assert "s01.notes" in plan.sync_keys


class _CountingBindings(tuple):
    """Tuple binding yang menghitung setiap kali diiterasi."""

    def __new__(cls, bindings: tuple[KeyBinding, ...]) -> Self:
        instance = super().__new__(cls, bindings)
        instance.iterations = 0
        return instance

    def __iter__(self):
        self.iterations += 1
        return super().__iter__()


def _scale_deck() -> DeckIR:
    """Bangun deck sintetis 300 slide dengan 20 binding per slide."""
    slides: list[SlideIR] = []
    bindings: list[KeyBinding] = []
    for index in range(300):
        slide_id = f"s{index + 1:03d}"
        blocks = [
            BlockIR(
                block_id=f"text{position}",
                block_type="text",
                span=None,
                role=None,
                fields={"text": f"Teks {position}", "heading": f"Judul {position}"},
            )
            for position in range(1, 11)
        ]
        if index % 50 == 0:
            blocks.append(
                BlockIR(
                    block_id="extra",
                    block_type="text",
                    span=None,
                    role=None,
                    fields={"text": "Ekstra", "heading": "Ekstra"},
                )
            )
        slides.append(SlideIR(slide_id, "content", index, tuple(blocks), None))
        for position in range(1, 11):
            for leaf in ("text", "heading"):
                bindings.append(
                    KeyBinding(
                        key=f"{slide_id}.text{position}.{leaf}",
                        slide_id=slide_id,
                        block_id=f"text{position}",
                        leaf=leaf,
                        kind="text",
                        sync=True,
                        yaml_path=("slides", index, "blocks", position - 1, leaf),
                        value="nilai",
                        plain_text="nilai",
                    )
                )
    return DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Scale Deck"},
        theme_name="indigo",
        slides=tuple(slides),
        keys=KeyManifest(_CountingBindings(tuple(bindings))),
    )


def _reference_unkeyed_visible(deck: DeckIR) -> tuple[str, ...]:
    """Hitung unkeyed_visible dengan pemindaian binding per slide."""
    bindings = deck.keys.bindings
    declarations: dict[str, set[str]] = {}
    for binding in bindings:
        if binding.block_id is None:
            continue
        namespace = f"{binding.slide_id}.{binding.block_id}"
        declarations.setdefault(namespace, set()).add(binding.leaf)

    unkeyed: list[str] = []
    for slide in deck.slides:
        for block in slide.blocks:
            namespace = f"{slide.slide_id}.{block.block_id}"
            if set(_expected_leaves(block)) - declarations.get(namespace, set()):
                unkeyed.append(namespace)
    return tuple(unkeyed)


def test_scale_plan_matches_reference_and_keeps_binding_scans_linear() -> None:
    deck = _scale_deck()

    plan = build_coverage_plan(deck)
    iterations = deck.keys.bindings.iterations
    reference = _reference_unkeyed_visible(deck)

    assert len(deck.slides) == 300
    assert len(deck.keys.bindings) == 6000
    assert plan.unkeyed_visible == reference
    assert "s001.extra" in plan.unkeyed_visible
    assert plan.missing_alt == ()
    assert plan.charts == ()
    assert plan.ok is False
    assert iterations <= 8

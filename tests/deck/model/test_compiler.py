"""Test compiler deterministik, IR, dan batas import model."""

from pathlib import Path

from autooffice.deck.model import (
    compile_deck,
    compile_deck_file,
    load_deck,
    loads_deck,
)

_MODEL_DIR = Path(__file__).resolve().parents[3] / "src" / "autooffice" / "deck" / "model"


def _signature(deck) -> tuple[object, ...]:
    return tuple(
        (
            slide.slide_id,
            slide.layout,
            slide.order,
            slide.notes,
            slide.rows,
            tuple(
                (block.block_id, block.block_type, block.span, block.role, block.fields)
                for block in slide.blocks
            ),
        )
        for slide in deck.slides
    )


def test_compile_is_deterministic(fixture_dir: Path) -> None:
    path = fixture_dir / "all-blocks.yaml"
    first = compile_deck(load_deck(path))
    second = compile_deck(load_deck(path))

    assert first.keys == second.keys
    assert _signature(first) == _signature(second)


def test_compile_file_matches_load_and_compile(fixture_dir: Path) -> None:
    path = fixture_dir / "minimal.yaml"
    direct = compile_deck_file(path)
    loaded = compile_deck(load_deck(path))

    assert direct.keys == loaded.keys


def test_compile_custom_rows_flattens_in_order(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "custom-grid.yaml"))

    assert tuple(block.block_id for block in deck.slides[0].blocks) == (
        "eyebrow",
        "title",
        "lead",
        "chart2",
        "insight",
    )


def test_compile_custom_rows_match_authoring_order(fixture_dir: Path) -> None:
    slide = compile_deck(load_deck(fixture_dir / "custom-grid.yaml")).slides[0]

    assert slide.rows == (
        ("eyebrow",),
        ("title", "lead"),
        ("chart2", "insight"),
    )
    assert tuple(block_id for row in slide.rows for block_id in row) == tuple(
        block.block_id for block in slide.blocks
    )


def test_compile_preset_slides_keep_empty_rows(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "minimal.yaml"))

    assert tuple(slide.rows for slide in deck.slides) == ((),)


def test_compile_preserves_notes(fixture_dir: Path) -> None:
    slide = compile_deck(load_deck(fixture_dir / "minimal.yaml")).slides[0]

    assert slide.notes == (
        "Catatan pembicara untuk slide pertama.\nBaris kedua tetap dipertahankan."
    )


def test_meta_language_is_normalized_in_ir(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "all-blocks.yaml"))

    assert deck.meta["language"] == "en"


def test_slide_order_matches_compiled_index(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "minimal.yaml"))

    assert tuple(slide.order for slide in deck.slides) == (0,)


def test_block_id_source_is_allowed_without_slide_source() -> None:
    text = """\
schema: autooffice.deck/v1
meta: {title: "Source id", author: "Tim"}
slides:
  - id: s01
    layout: content
    blocks:
      - {id: source, type: text, text: "Teks"}
"""

    deck = compile_deck(loads_deck(text))

    assert deck.slides[0].blocks[0].block_id == "source"


def test_model_modules_do_not_import_renderer_google_pptx_or_com() -> None:
    forbidden = (
        "autooffice.deck.render",
        "autooffice.google",
        "python-pptx",
        "import pptx",
        "win32com",
    )

    for path in sorted(_MODEL_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"{path.name} memuat {marker}"

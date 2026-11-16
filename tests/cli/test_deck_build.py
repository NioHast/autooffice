"""Tes build deck YAML: PPTX, Slides, dry-run, aset, dan transcript."""

from pathlib import Path

import pytest
from pptx import Presentation

from autooffice.cli import CliError
from autooffice.cli.build import build_deck
from autooffice.cli.main import main


def _state_file(deck_path: Path) -> Path:
    return deck_path.parent / ".autooffice" / "state" / f"{deck_path.stem}.json"


def test_build_pptx_writes_named_output_and_transcript(
    deck_path: Path,
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"
    outcome = build_deck(deck_path, ("pptx",), out)

    assert (out / "deck.pptx").is_file()
    assert (out / "deck.transcript.md").read_bytes() == (
        deck_path.parent / "transcripts.md"
    ).read_bytes()
    assert outcome.files == (out / "deck.pptx", out / "deck.transcript.md")
    assert outcome.warnings == ()
    assert "deck: Deck Uji Build" in outcome.notes
    assert "slide: 4" in outcome.notes
    assert "coverage: 20 key, 1 chart, 0 temuan" in outcome.notes
    assert not _state_file(deck_path).exists()
    assert not (out / ".autooffice-build" / deck_path.stem).exists()

    presentation = Presentation(str(out / "deck.pptx"))
    assert len(presentation.slides) == 4
    assert any(
        shape.name.startswith("autooffice:image:s04.image1")
        for shape in presentation.slides[3].shapes
    )


def test_build_pptx_rejects_pdf_target(deck_path: Path, tmp_path: Path) -> None:
    with pytest.raises(CliError, match="target tidak valid") as error:
        build_deck(deck_path, ("pdf",), tmp_path / "out")

    assert error.value.code == "CLI-TARGET-INVALID"
    assert error.value.exit_code == 2


def test_build_pptx_rejects_all_target(deck_path: Path, tmp_path: Path) -> None:
    with pytest.raises(CliError, match="target tidak valid") as error:
        build_deck(deck_path, ("all",), tmp_path / "out")

    assert error.value.code == "CLI-TARGET-INVALID"
    assert error.value.exit_code == 2


def test_build_pptx_keep_intermediate_preserves_staged_assets(
    deck_path: Path,
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"
    build_deck(deck_path, ("pptx",), out, keep_intermediate=True)

    build_dir = deck_path.parent / ".autooffice-build" / deck_path.stem
    assert (build_dir / "assets" / "hero.png").is_file()
    assert (build_dir / "diagrams" / "flow.puml").is_file()


def test_build_missing_asset_fails_with_slide_block_and_path(
    missing_asset_deck_path: Path,
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"
    with pytest.raises(
        CliError,
        match=r"slide 's04'.*block 'image1'.*assets/missing\.png",
    ) as error:
        build_deck(missing_asset_deck_path, ("pptx",), out)

    assert error.value.code == "CLI-ASSET"
    assert error.value.exit_code == 1
    assert not out.exists()


def test_build_dry_run_pptx_and_slides_writes_nothing(
    deck_path: Path,
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"
    outcome = build_deck(
        deck_path,
        ("pptx", "slides"),
        out,
        dry_run=True,
        google_services=object(),
    )

    assert outcome.dry_run is True
    assert out / "deck.pptx" in outcome.files
    assert out / "deck.transcript.md" in outcome.files
    assert _state_file(deck_path) in outcome.files
    assert out / "deck.slides-upload.pptx" not in outcome.files
    assert any("Google Slides: push staging" in note for note in outcome.notes)
    assert not out.exists()
    assert not _state_file(deck_path).exists()
    assert not (deck_path.parent / ".autooffice-build").exists()


def test_build_deck_copy_error_stops_before_render(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from autooffice.deck.copy.diagnostics import Diagnostic

    def fake_check_copy(*_args: object, **_kwargs: object) -> tuple[Diagnostic, ...]:
        return (
            Diagnostic(
                rule="banned_phrases",
                severity="error",
                key="s01.title.text",
                message="Frasa terlarang.",
                hint="Ganti frasa.",
            ),
        )

    monkeypatch.setattr("autooffice.deck.copy.check_copy", fake_check_copy)
    monkeypatch.setattr("autooffice.deck.copy.has_errors", lambda _diagnostics: True)
    out = tmp_path / "out"

    with pytest.raises(CliError, match="copy checker") as error:
        build_deck(deck_path, ("pptx",), out)

    assert error.value.code == "CLI-COPY"
    assert not out.exists()


def test_main_build_deck_pptx_prints_concise_summary(
    deck_path: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "out"
    assert main(["build", str(deck_path), "--target", "pptx", "--out", str(out)]) == 0
    captured = capsys.readouterr()

    assert str(out / "deck.pptx") in captured.out
    assert "deck: Deck Uji Build" in captured.out
    assert "slide: 4" in captured.out
    assert "coverage: 20 key, 1 chart, 0 temuan" in captured.out
    assert "font-embedding" not in captured.err

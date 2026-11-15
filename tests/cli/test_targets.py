"""Tes matriks target, deteksi input, dan target doctor."""

from pathlib import Path

import pytest

from autooffice.cli import CliError
from autooffice.cli.targets import (
    DOCTOR_TARGETS,
    InputKind,
    canonical_targets,
    default_check_targets,
    detect_input_kind,
    parse_doctor_targets,
    parse_targets,
)


@pytest.mark.parametrize(
    ("raw", "suffix", "expected"),
    [
        ("docx", ".md", ("docx",)),
        ("docx,docx", ".md", ("docx",)),
        ("pptx", ".yaml", ("pptx",)),
        ("slides", ".yaml", ("slides",)),
        ("slides, pptx", ".yaml", ("pptx", "slides")),
        ("pptx,slides,pptx", ".yaml", ("pptx", "slides")),
    ],
)
def test_parse_targets_matrix(raw: str, suffix: str, expected: tuple[str, ...]) -> None:
    kind = detect_input_kind(Path(f"input{suffix}"))
    assert parse_targets(raw, kind) == expected


@pytest.mark.parametrize(
    ("raw", "suffix", "match"),
    [
        ("pdf", ".md", "target tidak valid"),
        ("docx,pdf", ".md", "target tidak valid"),
        ("all", ".md", "target tidak valid"),
        ("all,docx", ".md", "target tidak valid"),
        ("pdf", ".yaml", "target tidak valid"),
        ("pptx,pdf", ".yaml", "target tidak valid"),
        ("all", ".yaml", "target tidak valid"),
        ("all,pptx", ".yaml", "target tidak valid"),
        ("ppt", ".md", "target tidak valid"),
        ("pptx", ".md", "target tidak valid"),
        ("docx", ".yaml", "target tidak valid"),
        ("", ".md", "tidak valid"),
        ("docx,,pptx", ".md", "tidak valid"),
    ],
)
def test_parse_targets_rejects_invalid(raw: str, suffix: str, match: str) -> None:
    kind = detect_input_kind(Path(f"input{suffix}"))
    with pytest.raises(CliError, match=match):
        parse_targets(raw, kind)


def test_parse_targets_requires_target_for_build() -> None:
    with pytest.raises(CliError, match="wajib"):
        parse_targets(None, InputKind.MARKDOWN)


def test_parse_targets_optional_for_check() -> None:
    assert parse_targets(None, InputKind.DECK, required=False) == canonical_targets(InputKind.DECK)


def test_default_check_targets_cover_all_valid_targets() -> None:
    assert default_check_targets(InputKind.MARKDOWN) == ("docx",)
    assert default_check_targets(InputKind.DECK) == ("pptx", "slides")


@pytest.mark.parametrize("name", ["document.txt", "document.json", "document"])
def test_detect_input_kind_rejects_unknown_suffix(name: str) -> None:
    with pytest.raises(CliError, match=r"\.md atau \.yaml"):
        detect_input_kind(Path(name))


def test_parse_doctor_targets_none() -> None:
    assert parse_doctor_targets(None) is None


def test_parse_doctor_targets_canonical_order() -> None:
    assert parse_doctor_targets("pptx, docx") == ("docx", "pptx")


def test_parse_doctor_targets_rejects_all() -> None:
    with pytest.raises(CliError, match="target doctor tidak valid"):
        parse_doctor_targets("all")


def test_parse_doctor_targets_rejects_pdf() -> None:
    with pytest.raises(CliError, match="target doctor tidak valid"):
        parse_doctor_targets("docx,pdf")


def test_doctor_targets_match_cli_surface() -> None:
    assert DOCTOR_TARGETS == ("docx", "pptx", "slides")

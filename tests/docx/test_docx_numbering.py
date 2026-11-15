"""Tes unit helper angka Romawi dan penghapusan parsing nomor bab dari teks."""

import pytest

from autooffice.docx.package.numbering import roman_to_int, to_roman

ROMAN_CASES: tuple[tuple[str, int | None], ...] = (
    ("I", 1),
    ("IV", 4),
    ("IX", 9),
    ("XIV", 14),
    ("MCMXCIV", 1994),
    ("xiv", 14),
    ("", None),
    ("ABC", None),
    # Non-kanonis, tetapi simbolnya tetap dijumlahkan menjadi 4.
    ("IIII", 4),
)


@pytest.mark.parametrize(("token", "expected"), ROMAN_CASES)
def test_roman_to_int(token: str, expected: int | None) -> None:
    assert roman_to_int(token) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (1, "I"),
        (4, "IV"),
        (9, "IX"),
        (14, "XIV"),
        (40, "XL"),
        (1994, "MCMXCIV"),
        (0, ""),
        (-1, ""),
    ),
)
def test_to_roman(value: int, expected: str) -> None:
    assert to_roman(value) == expected


def test_roman_roundtrip() -> None:
    for value in range(1, 101):
        assert roman_to_int(to_roman(value)) == value


def test_text_based_chapter_number_helpers_are_removed() -> None:
    """Nomor bab dihitung dari urutan heading, bukan dari teks ``BAB I``."""

    from autooffice.docx import markdown
    from autooffice.docx.package import captions, layout, numbering

    for name in ("chapter_number", "format_roman", "CHAPTER_RE", "ARABIC_CHAPTER_RE"):
        assert not hasattr(numbering, name), f"numbering masih punya {name}"
    for name in ("NumberingSpec", "HeadingNumberer", "format_chapter_number", "roman"):
        assert not hasattr(markdown, name), f"markdown masih punya {name}"
    assert not hasattr(layout, "roman_to_int")
    assert not hasattr(layout, "chapter_number")
    assert not hasattr(captions, "chapter_number")
    assert not hasattr(captions, "_chapter_number")

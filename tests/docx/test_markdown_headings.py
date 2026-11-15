"""Tes unit persiapan heading Markdown dan ``balance_title``.

Nomor heading tidak lagi ditulis ke Markdown; tes ini memastikan hanya
uppercase H1 bernomor, raw inline ``w:br`` untuk ``BAB_ROMAN``, dan heading
``unnumbered``/H2-H6 tidak berubah.
"""

import pytest

from autooffice.docx.markdown.headings import (
    LINE_BREAK,
    balance_title,
    finalize_markdown_headings,
    parse_heading,
    uppercase_markdown,
)


def test_parse_heading_attributes_and_unnumbered() -> None:
    parsed = parse_heading("## Judul Sub {#sub .unnumbered} ##")
    assert parsed is not None
    assert parsed.level == 2
    assert parsed.text == "Judul Sub"
    assert parsed.attributes == "{#sub .unnumbered}"
    assert parsed.unnumbered is True

    shorthand = parse_heading("# Abstrak {-}")
    assert shorthand is not None
    assert shorthand.unnumbered is True

    assert parse_heading("    # kode") is None
    assert parse_heading("Teks # bukan heading") is None


def test_uppercase_heading_preserves_inline_and_url() -> None:
    text = "Sub *miring* [tautan](HTTP://EXAMPLE.COM) `kode`"
    assert uppercase_markdown(text) == "SUB *MIRING* [TAUTAN](HTTP://EXAMPLE.COM) `kode`"


def test_finalize_h1_roman_uppercase_and_line_break() -> None:
    output = finalize_markdown_headings("# Pendahuluan\n", body="BAB_ROMAN")

    assert output == f"# {LINE_BREAK}PENDAHULUAN\n"


def test_finalize_h1_arabic_uppercase_without_line_break() -> None:
    output = finalize_markdown_headings("# Pendahuluan\n", body="ARABIC_DOTTED")

    assert output == "# PENDAHULUAN\n"


def test_finalize_h1_preserves_attributes() -> None:
    output = finalize_markdown_headings("# Pendahuluan {#bab-1}\n", body="BAB_ROMAN")

    assert output == f"# {LINE_BREAK}PENDAHULUAN {{#bab-1}}\n"


def test_finalize_h1_unnumbered_is_unchanged() -> None:
    markdown = "# Lampiran {-}\n\n# Ringkasan {.unnumbered}\n"

    output = finalize_markdown_headings(markdown, body="BAB_ROMAN")

    assert output == markdown


def test_finalize_h2_h6_are_unchanged() -> None:
    markdown = "## Latar Belakang\n\n### Detail {#detail}\n\n###### Level Enam\n"

    output = finalize_markdown_headings(markdown, body="BAB_ROMAN")

    assert output == markdown


def test_finalize_skips_fenced_code() -> None:
    markdown = "```markdown\n# bukan heading\n## juga bukan\n```\n\n# Pendahuluan\n"

    output = finalize_markdown_headings(markdown, body="BAB_ROMAN")

    assert "# bukan heading" in output
    assert "## juga bukan" in output
    assert f"# {LINE_BREAK}PENDAHULUAN\n" in output


def test_finalize_rejects_unknown_body() -> None:
    with pytest.raises(ValueError, match="tidak dikenal"):
        finalize_markdown_headings("# Judul\n", body="ROMAN")


def test_balance_title_short_title_single_line() -> None:
    assert balance_title("Laporan Tugas") == ("Laporan Tugas",)
    assert balance_title("") == ("",)
    assert balance_title("x" * 80) == ("x" * 80,)


def test_balance_title_two_long_words_does_not_crash() -> None:
    text = ("A" * 30) + " " + ("B" * 30)
    assert len(text) > 55

    lines = balance_title(text)

    assert lines == ("A" * 30, "B" * 30)
    assert " ".join(lines) == text


def test_balance_title_splits_long_title() -> None:
    text = "Optimasi Pipeline Pemrosesan Dokumen Markdown untuk Laporan Tugas Akhir"

    lines = balance_title(text)

    assert 2 <= len(lines) <= 3
    assert " ".join(lines) == text
    assert max(len(line) for line in lines) < len(text)

"""Penomoran heading body DOCX dengan numbering native Word.

Modul ini tidak lagi menulis nomor sebagai teks. Nomor H1/H2/H3 dihasilkan
Word dari ``word/numbering.xml`` + ``w:numPr`` pada style ``Heading1``..
``Heading3`` (lihat :mod:`autooffice.docx.package.native_numbering`). Tugas
modul ini adalah mengenali heading tak bernomor dan memasang override
``w:numPr`` ``numId=0`` pada paragrafnya.

Deteksi ``unnumbered`` dipertahankan dari implementasi lama: marker ``{-}``,
class ``.unnumbered`` pada nama style, nama front/back matter baku, dan
subbab di bawah H1 tak bernomor. Tidak ada run heading yang dibangun ulang;
isi paragraf tidak disentuh.

Catatan coupling: label bab hanya muncul sebagai list label karena nomor
tidak ada di teks heading. Word yang menampilkan label tersebut.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Literal

from lxml import etree

from . import DocxError, paragraphs
from .names import normalize_style_id
from .native_numbering import (
    NumberingSpec,
    paragraph_numbering,
    set_paragraph_unnumbered,
)
from .package import DOCUMENT_PART, DocumentPackage
from .xml import iter_paragraphs, tree_digest

ChapterRole = Literal["front_matter", "body", "back_matter", "unnumbered"]

_CHAPTER_STYLES = frozenset({"heading1", "chaptertitle"})


def _is_chapter_style(style_id: str | None) -> bool:
    return normalize_style_id(style_id) in _CHAPTER_STYLES


_HEADING_LEVELS = frozenset({1, 2, 3})
_FRONT_MATTER_NAMES = frozenset(
    {
        "KATA PENGANTAR",
        "PRAKATA",
        "UCAPAN TERIMA KASIH",
        "ABSTRAK",
        "ABSTRACT",
        "DAFTAR ISI",
        "DAFTAR TABEL",
        "DAFTAR GAMBAR",
        "DAFTAR LAMPIRAN",
        "DAFTAR SINGKATAN",
        "DAFTAR SIMBOL",
        "DAFTAR PUSTAKA",
        "DAFTAR RUJUKAN",
        "BIBLIOGRAFI",
        "MOTTO",
        "PERSEMBAHAN",
    }
)
_UNNUMBERED_PREFIXES = (
    "LEMBAR PENGESAHAN",
    "HALAMAN PENGESAHAN",
    "LEMBAR PERSETUJUAN",
    "HALAMAN PERSETUJUAN",
    "LEMBAR PERNYATAAN",
    "HALAMAN PERNYATAAN",
    "PERNYATAAN ",
    "LAMPIRAN",
)
_EXPLICIT_UNNUMBERED_RE = re.compile(r"^\s*\{-\}\s*")


class HeadingError(DocxError):
    """Heading tidak valid atau level tidak didukung."""

    default_code = "HEADING"


class Heading:
    """Satu heading body beserta status penomorannya."""

    __slots__ = ("level", "paragraph", "text", "unnumbered")

    def __init__(
        self,
        level: int,
        paragraph: etree._Element,
        text: str,
        unnumbered: bool,
    ) -> None:
        self.level = level
        self.paragraph = paragraph
        self.text = text
        self.unnumbered = unnumbered

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Heading):
            return NotImplemented
        return (
            self.level == other.level
            and self.paragraph is other.paragraph
            and self.text == other.text
            and self.unnumbered == other.unnumbered
        )

    def __repr__(self) -> str:
        return f"Heading(level={self.level!r}, text={self.text!r}, unnumbered={self.unnumbered!r})"


class HeadingReport:
    """Ringkasan hasil :func:`apply_heading_numbering`."""

    __slots__ = (
        "changed",
        "headings",
        "numbered",
        "skipped_without_chapter",
        "unnumbered",
    )

    def __init__(
        self,
        *,
        changed: bool,
        numbered: int,
        unnumbered: int,
        skipped_without_chapter: int,
        headings: tuple[Heading, ...],
    ) -> None:
        self.changed = changed
        self.numbered = numbered
        self.unnumbered = unnumbered
        self.skipped_without_chapter = skipped_without_chapter
        self.headings = headings


def _normalized(text: str) -> str:
    return " ".join(text.split())


def is_unnumbered(paragraph: etree._Element) -> bool:
    """True untuk heading yang tidak boleh mendapat nomor bab.

    Mendukung marker eksplisit ``{-}``, style yang mengandung
    ``unnumbered``, serta heading front/back matter yang lazim. ``ChapterTitle``
    diperlakukan sebagai kandidat bab agar klasifikasi caption/persamaan sama.
    """

    style = paragraphs.paragraph_style_id(paragraph) or ""
    if paragraphs.heading_level(paragraph) is None and not _is_chapter_style(style):
        return False
    if "unnumbered" in style.casefold():
        return True
    text = paragraphs.paragraph_text(paragraph).strip()
    if _EXPLICIT_UNNUMBERED_RE.match(text):
        return True
    normalized = _normalized(text).upper()
    if not normalized:
        return True
    if normalized in _FRONT_MATTER_NAMES:
        return True
    return any(
        normalized == prefix.rstrip() or normalized.startswith(prefix)
        for prefix in _UNNUMBERED_PREFIXES
    )


def is_numbered_heading(paragraph: etree._Element) -> bool:
    """True bila paragraf heading memakai numbering, dengan fallback teks.

    Override ``numId=0`` adalah sumber utama setelah
    :func:`apply_heading_numbering` berjalan. Sebelum override ada, deteksi
    jatuh ke :func:`is_unnumbered` agar fixture dan dokumen lama tetap terbaca.
    """

    numbering = paragraph_numbering(paragraph)
    if numbering is not None:
        return numbering[1] != 0
    return not is_unnumbered(paragraph)


def iter_chapter_candidates(package: DocumentPackage) -> tuple[Heading, ...]:
    """H1 dan ``ChapterTitle`` dalam urutan dokumen."""

    root = package.xml(DOCUMENT_PART)
    candidates: list[Heading] = []
    for paragraph in iter_paragraphs(root):
        style = paragraphs.paragraph_style_id(paragraph)
        level = paragraphs.heading_level(paragraph)
        if level != 1 and not _is_chapter_style(style):
            continue
        candidates.append(
            Heading(
                level=1,
                paragraph=paragraph,
                text=paragraphs.paragraph_text(paragraph).strip(),
                unnumbered=is_unnumbered(paragraph),
            )
        )
    return tuple(candidates)


def _title_key(text: str) -> str:
    return _normalized(text).casefold()


def classify_chapters(
    package: DocumentPackage,
    *,
    body_titles: Sequence[str] = (),
    has_back_matter: bool = True,
) -> Mapping[etree._Element, ChapterRole]:
    """Peta elemen paragraf kandidat H1/ChapterTitle ke perannya.

    Bila ``body_titles`` diberikan (dari ``structure.body``), H1 dicocokkan
    berurutan dengan judul bab. H1 sebelum bab pertama adalah front matter,
    H1 setelah bab terakhir adalah back matter, dan H1 tak dikenal di tengah
    adalah heading unnumbered. Tanpa ``body_titles``, fallback memakai
    ``is_numbered_heading``/``is_unnumbered``.
    """

    titles = tuple(_title_key(title) for title in body_titles)
    roles: dict[etree._Element, ChapterRole] = {}
    expected = 0
    entered_body = False
    for heading in iter_chapter_candidates(package):
        key = _title_key(heading.text)
        if titles:
            if expected < len(titles) and key == titles[expected]:
                roles[heading.paragraph] = "body"
                entered_body = True
                expected += 1
            elif not entered_body:
                roles[heading.paragraph] = "front_matter"
            elif expected >= len(titles) and has_back_matter:
                roles[heading.paragraph] = "back_matter"
            else:
                roles[heading.paragraph] = "unnumbered"
            continue
        if is_numbered_heading(heading.paragraph):
            roles[heading.paragraph] = "body"
            entered_body = True
        elif not entered_body:
            roles[heading.paragraph] = "front_matter"
        elif has_back_matter:
            roles[heading.paragraph] = "back_matter"
        else:
            roles[heading.paragraph] = "unnumbered"
    return roles


def iter_chapter_headings(
    package: DocumentPackage,
    *,
    body_titles: Sequence[str] = (),
    has_back_matter: bool = True,
) -> tuple[Heading, ...]:
    """H1/ChapterTitle yang menjadi bab bernomor (role ``body``)."""

    roles = classify_chapters(
        package,
        body_titles=body_titles,
        has_back_matter=has_back_matter,
    )
    return tuple(
        heading
        for heading in iter_chapter_candidates(package)
        if roles.get(heading.paragraph) == "body"
    )


def iter_headings(package: DocumentPackage) -> tuple[Heading, ...]:
    """Iterasi heading body dalam urutan dokumen."""

    root = package.xml(DOCUMENT_PART)
    headings: list[Heading] = []
    for paragraph in iter_paragraphs(root):
        level = paragraphs.heading_level(paragraph)
        if level is None:
            continue
        headings.append(
            Heading(
                level=level,
                paragraph=paragraph,
                text=paragraphs.paragraph_text(paragraph).strip(),
                unnumbered=is_unnumbered(paragraph),
            )
        )
    return tuple(headings)


def apply_heading_numbering(
    package: DocumentPackage,
    spec: NumberingSpec,
    *,
    body_titles: Sequence[str] = (),
    has_back_matter: bool = True,
) -> HeadingReport:
    """Matikan numbering style pada heading tak bernomor.

    ``body_titles`` berasal dari ``structure.body`` dan menentukan H1 mana
    yang bernomor serta H1 mana yang front/back matter atau unnumbered. H2/H3
    sebelum H1 bernomor dan H2/H3 di bawah H1 tak bernomor juga memakai
    ``numId=0`` agar tidak mewarisi counter bab terakhir. Tidak ada teks
    heading yang diubah.
    """

    if not isinstance(spec, NumberingSpec):
        raise HeadingError("spec penomoran heading tidak valid")

    before = tree_digest(package.xml(DOCUMENT_PART))
    roles = classify_chapters(
        package,
        body_titles=body_titles,
        has_back_matter=has_back_matter,
    )
    chapter = 0
    numbered = 0
    unnumbered = 0
    skipped = 0
    in_unnumbered_section = False

    for heading in iter_headings(package):
        if heading.level not in _HEADING_LEVELS:
            continue
        paragraph = heading.paragraph
        if heading.level == 1:
            role = roles.get(paragraph, "unnumbered")
            if role == "body":
                in_unnumbered_section = False
                chapter += 1
                numbered += 1
                continue
            in_unnumbered_section = True
            unnumbered += 1
            set_paragraph_unnumbered(paragraph)
            continue
        if in_unnumbered_section:
            unnumbered += 1
            set_paragraph_unnumbered(paragraph)
            continue
        if chapter == 0:
            skipped += 1
            set_paragraph_unnumbered(paragraph)
            continue
        numbered += 1

    after = tree_digest(package.xml(DOCUMENT_PART))
    return HeadingReport(
        changed=before != after,
        numbered=numbered,
        unnumbered=unnumbered,
        skipped_without_chapter=skipped,
        headings=iter_headings(package),
    )


def heading_bookmark_name(heading: Heading) -> str:
    """Nama bookmark stabil untuk PAGEREF/TOC berbasis teks judul."""

    safe = re.sub(r"[^A-Za-z0-9]+", "_", heading.text).strip("_")
    if safe:
        return f"_Toc{safe[:40]}"
    return f"_TocHeading{heading.level}"


__all__ = [
    "ChapterRole",
    "Heading",
    "HeadingError",
    "HeadingReport",
    "NumberingSpec",
    "apply_heading_numbering",
    "classify_chapters",
    "heading_bookmark_name",
    "is_numbered_heading",
    "is_unnumbered",
    "iter_chapter_candidates",
    "iter_chapter_headings",
    "iter_headings",
    "paragraph_numbering",
]

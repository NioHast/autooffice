"""Persiapan heading Markdown sebelum Pandoc dengan numbering native.

Nomor heading tidak lagi ditulis ke Markdown. Nomor dihasilkan Word dari
``w:numPr`` pada style ``Heading1``..``Heading3`` (lihat
``package/native_numbering.py``). Modul ini hanya:

- meng-uppercase judul H1 yang bernomor (perilaku tampilan lama);
- menyisipkan raw inline ``<w:br/>`` sebelum judul H1 ``BAB_ROMAN`` agar
  label ``BAB N`` dan judul tetap dua baris seperti baseline;
- membiarkan H2-H6 dan heading ``unnumbered`` apa adanya.

Tidak ada akses ZIP, XML, atau package. Semua fungsi murni menerima dan
mengembalikan teks Markdown.
"""

import math
import re
from dataclasses import dataclass

__all__ = [
    "MarkdownHeading",
    "balance_title",
    "finalize_markdown_headings",
    "heading_level",
    "is_unnumbered",
    "parse_heading",
    "uppercase_markdown",
]

_SUPPORTED_BODY = frozenset({"BAB_ROMAN", "ARABIC_DOTTED"})

_HEADING_RE = re.compile(r"^(?P<indent> {0,3})(?P<hashes>#{1,6})(?P<space>[ \t]+)(?P<body>.*)$")
_CLOSING_HASHES_RE = re.compile(r"[ \t]+#+[ \t]*$")
_ATTRIBUTE_RE = re.compile(r"(?P<space>[ \t]+)(?P<attributes>\{[^{}]*\})[ \t]*$")
_FENCE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")
_LINK_RE = re.compile(r"(?P<open>!?\[)(?P<label>[^\]]*)(?P<close>\]\([^)]*\))")
_CODE_SPAN_RE = re.compile(r"(?P<ticks>`+)(?:(?!(?P=ticks)).)*?(?P=ticks)")
_HTML_TAG_RE = re.compile(r"<[^>]*>")

# Raw inline OpenXML yang menjadi ``w:br`` setelah Pandoc.
LINE_BREAK = "`<w:br/>`{=openxml}"


@dataclass(frozen=True, slots=True)
class MarkdownHeading:
    """Hasil parsing satu baris heading ATX."""

    level: int
    text: str
    attributes: str
    indent: str
    unnumbered: bool
    raw: str


def _protect_inline(text: str) -> tuple[str, list[str]]:
    """Ganti code span dan tujuan link dengan placeholder agar aman di-upper."""

    protected: list[str] = []

    def store(value: str) -> str:
        protected.append(value)
        return f"\x00{len(protected) - 1}\x00"

    text = _CODE_SPAN_RE.sub(lambda match: store(match.group(0)), text)
    text = _HTML_TAG_RE.sub(lambda match: store(match.group(0)), text)
    text = _LINK_RE.sub(
        lambda match: (
            match.group("open") + match.group("label").upper() + store(match.group("close"))
        ),
        text,
    )
    return text, protected


def uppercase_markdown(text: str) -> str:
    """Uppercase teks Markdown tanpa mengubah code span/tujuan link.

    Judul H1 di-uppercase setelah inline formatting dipertahankan. Code span,
    tag HTML, dan URL di dalam link tidak boleh ikut berubah.
    """

    protected_text, protected = _protect_inline(text)
    upper = protected_text.upper()
    for index, value in enumerate(protected):
        upper = upper.replace(f"\x00{index}\x00", value)
    return upper


def _has_unnumbered_class(attributes: str) -> bool:
    inner = attributes.strip()
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1]
    tokens = inner.split()
    return "-" in tokens or ".unnumbered" in tokens or "unnumbered" in tokens


def parse_heading(line: str) -> MarkdownHeading | None:
    """Parse satu baris heading ATX; ``None`` jika bukan heading."""

    content = line.rstrip("\r\n")
    match = _HEADING_RE.match(content)
    if match is None:
        return None

    body = match.group("body")
    closing = _CLOSING_HASHES_RE.search(body)
    if closing is not None:
        body = body[: closing.start()]

    attributes = ""
    attribute_match = _ATTRIBUTE_RE.search(body)
    if attribute_match is not None:
        attributes = attribute_match.group("attributes")
        body = body[: attribute_match.start()]

    text = body.strip()
    return MarkdownHeading(
        level=len(match.group("hashes")),
        text=text,
        attributes=attributes,
        indent=match.group("indent"),
        unnumbered=_has_unnumbered_class(attributes),
        raw=line,
    )


def heading_level(line: str) -> int | None:
    """Level heading ATX pada baris, atau ``None``."""

    parsed = parse_heading(line)
    return parsed.level if parsed is not None else None


def is_unnumbered(line: str) -> bool:
    """True jika heading memakai ``{-}``/``.unnumbered``."""

    parsed = parse_heading(line)
    return bool(parsed is not None and parsed.unnumbered)


def _strip_line_ending(line: str) -> tuple[str, str]:
    content = line.rstrip("\r\n")
    return content, line[len(content) :]


def _fence_opening(line: str) -> tuple[str, int] | None:
    match = _FENCE_RE.match(line)
    if match is None:
        return None
    fence = match.group("fence")
    return fence[0], len(fence)


def _fence_closing(line: str, character: str, length: int) -> bool:
    pattern = re.compile(rf"^ {{0,3}}{re.escape(character)}{{{length},}}[ \t]*$")
    return pattern.match(line) is not None


def _render_numbered_h1(text: str, body: str) -> str:
    upper = uppercase_markdown(text)
    if body == "BAB_ROMAN":
        return f"{LINE_BREAK}{upper}"
    return upper


def finalize_markdown_headings(markdown: str, *, body: str = "BAB_ROMAN") -> str:
    """Siapkan heading Markdown untuk numbering native Word.

    H1 bernomor di-uppercase; ``BAB_ROMAN`` juga mendapat raw inline
    ``<w:br/>`` sebelum judul. H2-H6 dan heading ``unnumbered`` tidak diubah,
    termasuk atributnya. Fenced code block dilewati.
    """

    if body not in _SUPPORTED_BODY:
        raise ValueError(f"format penomoran body tidak dikenal: {body!r}")

    output: list[str] = []
    fence_character: str | None = None
    fence_length = 0

    for line in markdown.splitlines(keepends=True):
        content, ending = _strip_line_ending(line)

        if fence_character is not None:
            output.append(line)
            if _fence_closing(content, fence_character, fence_length):
                fence_character = None
                fence_length = 0
            continue

        opening = _fence_opening(content)
        if opening is not None:
            fence_character, fence_length = opening
            output.append(line)
            continue

        parsed = parse_heading(content)
        if parsed is None or not parsed.text or parsed.level != 1 or parsed.unnumbered:
            output.append(line)
            continue

        rendered = _render_numbered_h1(parsed.text, body)
        attributes = f" {parsed.attributes}" if parsed.attributes else ""
        output.append(f"{parsed.indent}# {rendered}{attributes}{ending}")

    return "".join(output)


# ---------------------------------------------------------------------------
# Pemecahan judul sampul (tidak terkait numbering)
# ---------------------------------------------------------------------------


def _count_words(text: str) -> int:
    return len(text.split())


def _max_line_length(lines: tuple[str, ...]) -> int:
    return max((len(line) for line in lines), default=0)


def _has_orphan(lines: tuple[str, ...]) -> bool:
    return any(_count_words(line) <= 1 for line in lines)


def _best_partition(words: list[str], line_count: int) -> tuple[str, ...] | None:
    """Partisi kata menjadi ``line_count`` baris dengan biaya minimum.

    Biaya sama dengan ``balance_title`` Lua: lebar baris terpanjang ditambah
    100 untuk setiap baris yatim (satu kata).
    """

    total = len(words)
    if line_count <= 0 or line_count > total:
        return None

    best: tuple[str, ...] | None = None
    best_cost = math.inf

    def recurse(
        start: int,
        remaining: int,
        current: tuple[str, ...],
        widest: int,
        orphans: int,
    ) -> None:
        nonlocal best, best_cost

        if remaining == 1:
            line = " ".join(words[start:])
            lines = (*current, line)
            width = max(widest, len(line))
            orphan_count = orphans + (1 if _count_words(line) <= 1 else 0)
            cost = width + 100 * orphan_count
            if cost < best_cost:
                best = lines
                best_cost = cost
            return

        # Sisakan minimal satu kata untuk setiap baris berikutnya.
        for end in range(start, total - remaining + 1):
            line = " ".join(words[start : end + 1])
            recurse(
                end + 1,
                remaining - 1,
                (*current, line),
                max(widest, len(line)),
                orphans + (1 if _count_words(line) <= 1 else 0),
            )

    recurse(0, line_count, (), 0, 0)
    return best


def balance_title(
    text: str,
    *,
    max_length: int = 55,
    max_line_width: int = 50,
) -> tuple[str, ...]:
    """Pecah judul menjadi baris seimbang.

    Guard khusus: judul dua kata yang lebih panjang dari ``max_length``
    dikembalikan sebagai dua baris, bukan ``None``, sehingga pemanggil tidak
    gagal saat mengindeks hasil.
    """

    stripped = text.strip()
    words = stripped.split()
    if not words:
        return ("",)
    if len(words) <= 1 or len(stripped) <= max_length:
        return (stripped,)

    two = _best_partition(words, 2)
    if two is not None and not _has_orphan(two) and _max_line_length(two) <= max_line_width:
        return two

    if len(words) >= 3:
        three = _best_partition(words, 3)
        if three is not None:
            return three

    # Guard: dua kata panjang tidak punya partisi tiga baris. Kembalikan
    # partisi dua baris agar pemanggil tidak menerima None/IndexError.
    if two is not None:
        return two
    return (stripped,)

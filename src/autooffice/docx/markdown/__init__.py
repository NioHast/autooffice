"""Parser Markdown bersama untuk fitur non-Pandoc.

Modul ini sengaja kecil dan bebas dari ``python-docx``/``lxml`` agar bisa
dipakai oleh Adeu, validasi, stage front matter, dan alat dev tanpa duplikasi
parser. Penomoran heading tidak lagi dilakukan di lapisan Markdown; nomor
dihasilkan Word dari style ``Heading1``..``Heading3``.
"""

from .blocks import (
    MarkdownBlock,
    MarkdownError,
    clean_text,
    iter_candidate_texts,
    load_markdown_blocks,
    load_markdown_directory,
    normalize_for_match,
    normalize_heading,
    normalize_inline,
    normalize_path,
    parse_markdown_blocks,
)
from .headings import (
    MarkdownHeading,
    balance_title,
    finalize_markdown_headings,
    heading_level,
    is_unnumbered,
    parse_heading,
    uppercase_markdown,
)

__all__ = [
    "MarkdownBlock",
    "MarkdownError",
    "MarkdownHeading",
    "balance_title",
    "clean_text",
    "finalize_markdown_headings",
    "heading_level",
    "is_unnumbered",
    "iter_candidate_texts",
    "load_markdown_blocks",
    "load_markdown_directory",
    "normalize_for_match",
    "normalize_heading",
    "normalize_inline",
    "normalize_path",
    "parse_heading",
    "parse_markdown_blocks",
    "uppercase_markdown",
]

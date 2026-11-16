"""Stage ``front_matter``: materialisasi Markdown sebelum Pandoc.

Front matter (sampul, lembar pengesahan, pernyataan, kata pengantar, abstrak,
dan kata kunci) ditulis langsung di ``document.md``. Stage ini hanya:

- membaca artifact ``plantuml.markdown`` milik stage plantuml;
- menyiapkan heading body untuk numbering native Word;
- mengganti marker ``<!-- section-break -->`` dengan raw OpenXML ``w:sectPr``
  yang ukuran halaman, margin, dan jarak header/footer-nya berasal dari
  ``format.yaml``;
- menulis ``front_matter.md``.

TOC dan daftar gambar/tabel **tidak** ditulis di sini; keduanya milik stage
post-Pandoc. Tidak ada fallback ke ``document.body`` atau artifact lain.

Referensi: https://pandoc.org/MANUAL.html
"""

import re
import time
from pathlib import Path
from typing import Any, ClassVar

from ..config import Format
from ..errors import DocgenError
from ..markdown.headings import (
    finalize_markdown_headings,
    parse_heading,
)
from ..package.page import PAGE_SIZES, page_size
from ..pipeline import BaseStage, StageName, StageResult

__all__ = [
    "SECTION_BREAK_MARKER",
    "FrontMatterError",
    "FrontMatterStage",
    "render_front_matter",
    "section_break",
]

SECTION_BREAK_MARKER = "<!-- section-break -->"
_SECTION_BREAK_RE = re.compile(rf"(?m)^[ \t]*{re.escape(SECTION_BREAK_MARKER)}[ \t]*$")


class FrontMatterError(DocgenError):
    """Front matter tidak dapat dirender dari data yang diberikan."""

    default_code = "FRONT-MATTER"


def _raw_openxml(xml: str) -> str:
    return f"```{{=openxml}}\n{xml}\n```"


def section_break(format: Format) -> str:
    """Section break penutup sampul dengan geometri dari ``format.yaml``."""

    page = format.page
    raw_size = str(page.size).upper()
    size = "Letter" if raw_size == "LETTER" else raw_size
    orientation = str(page.orientation).lower()
    if size not in PAGE_SIZES or orientation not in {"portrait", "landscape"}:
        raise FrontMatterError(
            f"ukuran halaman tidak didukung: {page.size}/{page.orientation}",
            code="FRONT-MATTER-PAGE",
            key="page.size",
        )
    width, height = page_size(size, orientation)
    orientation_attr = ' w:orient="landscape"' if orientation == "landscape" else ""
    margins = page.margins
    return _raw_openxml(
        "<w:p><w:pPr><w:sectPr>"
        '<w:footnotePr><w:numRestart w:val="eachSect"/></w:footnotePr>'
        f'<w:pgSz w:w="{width}" w:h="{height}"{orientation_attr}/>'
        f'<w:pgMar w:top="{margins.top}" w:right="{margins.right}" '
        f'w:bottom="{margins.bottom}" w:left="{margins.left}" '
        f'w:header="{page.header_distance}" w:footer="{page.footer_distance}" '
        f'w:gutter="{page.gutter}"/>'
        "</w:sectPr></w:pPr></w:p>"
    )


def _mark_appendix_unnumbered(markdown: str) -> str:
    """Tandai Heading 1 ``Lampiran`` dan turunannya sebagai unnumbered.

    ``# Lampiran`` adalah back matter yang mengikuti
    ``structure.back_matter.appendices``. Marker ``{-}``/``.unnumbered``
    membuat ``finalize_markdown_headings`` tidak meng-uppercase judul
    Lampiran; DOCX kemudian memasang override ``numId=0`` sehingga Lampiran
    tidak mendapat label ``BAB``. Heading 2/3 di bawah Lampiran juga tidak
    boleh mewarisi numbering subbab bab terakhir.
    """

    def with_marker(parsed: Any, line: str) -> str:
        content = line.rstrip("\r\n")
        attributes = parsed.attributes.strip()
        if attributes:
            inner = attributes[1:-1].strip()
            attributes = "{ " + " ".join(filter(None, (inner, ".unnumbered"))) + " }"
        else:
            attributes = "{-}"
        ending = line[len(content) :]
        return f"{parsed.indent}{'#' * parsed.level} {parsed.text} {attributes}{ending}"

    lines: list[str] = []
    in_appendix = False
    for line in markdown.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        parsed = parse_heading(content)
        if parsed is None or not parsed.text:
            lines.append(line)
            continue
        if parsed.level == 1:
            in_appendix = parsed.text.strip().casefold() == "lampiran"
            if in_appendix and not parsed.unnumbered:
                lines.append(with_marker(parsed, line))
                continue
        elif in_appendix and parsed.level in (2, 3) and not parsed.unnumbered:
            lines.append(with_marker(parsed, line))
            continue
        lines.append(line)
    return "".join(lines)


def render_front_matter(
    markdown: str,
    format: Format,
    *,
    numbering_body: str = "BAB_ROMAN",
) -> str:
    """Ganti marker section break dan siapkan heading body untuk Pandoc.

    ``markdown`` adalah isi ``document.md`` setelah front matter YAML,
    termasuk front matter Markdown dan body. Setiap baris yang hanya berisi
    ``<!-- section-break -->`` diganti dengan raw OpenXML dari
    :func:`section_break`. Heading H1 bernomor tetap di-uppercase dan Lampiran
    tetap unnumbered seperti sebelum fase 3b.
    """

    prepared = _mark_appendix_unnumbered(markdown)
    prepared = _SECTION_BREAK_RE.sub(lambda _match: section_break(format), prepared)
    return finalize_markdown_headings(prepared, body=numbering_body)


def _markdown_source(ctx: Any) -> str:
    """Sumber body satu-satunya: artifact ``plantuml.markdown`` dari stage plantuml.

    Tidak ada fallback ke ``document.body`` maupun ke artifact ``markdown``
    milik stage ini sendiri. Artifact yang tidak dideklarasikan atau tidak
    dapat dibaca adalah error input, bukan alasan memakai sumber cadangan.
    """

    artifacts = getattr(ctx, "artifacts", None)
    try:
        keys = tuple(artifacts.keys()) if artifacts is not None else ()
    except AttributeError, TypeError:
        keys = ()
    if artifacts is None or "plantuml.markdown" not in keys:
        raise FrontMatterError(
            "artifact 'plantuml.markdown' dari stage plantuml tidak tersedia",
            code="FRONT-MATTER-INPUT",
            key="plantuml.markdown",
        )
    path = Path(artifacts.get("plantuml.markdown"))
    if not path.is_file():
        raise FrontMatterError(
            f"artifact plantuml.markdown tidak ditemukan atau bukan file: {path}",
            code="FRONT-MATTER-INPUT",
            path=path,
        )
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise FrontMatterError(
            f"artifact plantuml.markdown tidak dapat dibaca: {exc}",
            code="FRONT-MATTER-INPUT",
            path=path,
        ) from exc


class FrontMatterStage(BaseStage):
    """Materialisasi Markdown sebelum ``pandoc``.

    Body hanya dibaca dari artifact ``plantuml.markdown`` milik stage plantuml;
    tidak ada fallback ke ``document.body`` atau artifact lain.
    """

    name: ClassVar[StageName] = StageName.FRONT_MATTER
    order: ClassVar[int] = 35
    requires: ClassVar[tuple[StageName, ...]] = (
        StageName.VALIDATE,
        StageName.PLANTUML,
        StageName.STYLE_REFERENCE,
    )
    mutates: ClassVar[frozenset[str]] = frozenset({"workspace"})
    idempotent: ClassVar[bool] = True

    def run(self, ctx: Any) -> StageResult:
        started = time.monotonic()
        ctx.workspace.ensure()
        path = ctx.workspace.path("front_matter.md")
        body = _markdown_source(ctx)
        text = render_front_matter(
            body,
            ctx.format,
            numbering_body=ctx.structure.numbering.body,
        )
        previous = path.read_text(encoding="utf-8") if path.is_file() else None
        changed = previous != text
        if changed:
            path.write_text(text, encoding="utf-8", newline="\n")

        # Output final untuk Pandoc memakai key standar ``markdown``. Stage
        # plantuml menyimpan bahan mentahnya di ``plantuml.markdown`` agar tidak
        # dianggap output stage ini saat build dijalankan ulang.
        keys = set(ctx.artifacts.keys())
        if "markdown" not in keys:
            ctx.artifacts.put("markdown", path)

        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={"markdown_bytes": len(text.encode("utf-8"))},
            artifacts=(path,),
        )

"""Stage ``sections``: section break, ukuran halaman, dan margin.

Stage ini memastikan dokumen hasil Pandoc memiliki section logis yang benar
sebelum stage lain bekerja:

- sampul berakhir pada section sendiri;
- front matter dan body tidak berbagi section;
- setiap Heading1 bernomor dan back matter dimulai pada section baru;
- seluruh section memakai ukuran halaman dan margin dari ``format.yaml``.

TOC, nomor halaman, dan header/footer bukan tanggung jawab stage ini. Nomor
heading body diterapkan sebelum section break agar heading bernomor ikut
terklasifikasi dengan benar.
"""

import time

from lxml import etree

from ..errors import StageError
from ..package.heading_numbering import (
    HeadingError,
    NumberingSpec,
    apply_heading_numbering,
    classify_chapters,
    iter_chapter_candidates,
)
from ..package.native_numbering import (
    NUMBERING_PART,
    NumberingError,
    verify_heading_numbering,
)
from ..package.package import DOCUMENT_PART, DocumentPackage
from ..package.page import page_size
from ..package.paragraphs import (
    body_children,
    document_body,
    heading_level,
    paragraph_style_id,
)
from ..package.sections import (
    SectionError,
    add_section_break,
    iter_sections,
    set_margins,
    set_page_size,
    set_section_type,
)
from ..package.xml import tree_digest
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix


class SectionsError(SectionError):
    """Konfigurasi section tidak dapat diterapkan."""

    default_code = "SECTION-STAGE"


def _document_hash(package: DocumentPackage) -> str:
    return tree_digest(package.xml(DOCUMENT_PART))


def _first_heading_after_cover(package: DocumentPackage) -> etree._Element | None:
    """Heading1 pertama setelah paragraf bergaya Cover*."""

    from ..package.names import W_P

    sections = iter_sections(package)
    if not sections:
        return None
    first = sections[0]
    children = body_children(document_body(package))
    last_cover = -1
    for index in range(first.start, first.end):
        child = children[index] if index < len(children) else None
        if child is not None and child.tag == W_P:
            style = paragraph_style_id(child)
            if style is not None and style.casefold().startswith("cover"):
                last_cover = index
    for index in range(max(last_cover + 1, first.start), first.end):
        child = children[index] if index < len(children) else None
        if child is not None and child.tag == W_P and heading_level(child) == 1:
            return child
    return None


def _break_headings(
    package: DocumentPackage,
    body_titles: tuple[str, ...],
    has_back_matter: bool,
) -> list[etree._Element]:
    """Heading yang wajib menjadi awal section baru.

    Hanya chapter body (dari ``structure.body``) dan back matter yang membuka
    section; front matter dan heading unnumbered di tengah body tidak. Deteksi
    memakai :func:`classify_chapters`, bukan nama teks.
    """

    roles = classify_chapters(
        package,
        body_titles=body_titles,
        has_back_matter=has_back_matter,
    )
    return [
        heading.paragraph
        for heading in iter_chapter_candidates(package)
        if roles.get(heading.paragraph) in {"body", "back_matter"}
    ]


def _apply_page_format(package: DocumentPackage, page: object) -> int:
    size = str(getattr(page, "size", "A4"))
    orientation = str(getattr(page, "orientation", "portrait"))
    try:
        width, height = page_size(size, orientation)
    except KeyError as exc:
        raise SectionsError(f"Ukuran halaman tidak dikenal: {size!r}") from exc
    margins = getattr(page, "margins", None)
    if margins is None:
        raise SectionsError("format.page.margins tidak tersedia")
    changed = 0
    for section in iter_sections(package):
        before = tree_digest(section.sect_pr)
        set_page_size(
            section,
            width=width,
            height=height,
            orientation=orientation,  # type: ignore[arg-type]
        )
        set_margins(
            section,
            top=int(margins.top),
            right=int(margins.right),
            bottom=int(margins.bottom),
            left=int(margins.left),
            header=int(getattr(page, "header_distance", 0)),
            footer=int(getattr(page, "footer_distance", 0)),
            gutter=int(getattr(page, "gutter", 0)),
        )
        if tree_digest(section.sect_pr) != before:
            changed += 1
    return changed


def _ensure_breaks(
    package: DocumentPackage,
    body_titles: tuple[str, ...],
    has_back_matter: bool,
) -> int:
    added = 0
    cover_heading = _first_heading_after_cover(package)
    if cover_heading is not None:
        sections = iter_sections(package)
        first = sections[0]
        children = body_children(document_body(package))
        index = children.index(cover_heading)
        if first.start < index < first.end:
            add_section_break(package, before=cover_heading, kind="nextPage")
            added += 1

    for heading in _break_headings(package, body_titles, has_back_matter):
        children = body_children(document_body(package))
        index = children.index(heading)
        sections = iter_sections(package)
        section = next(
            (item for item in sections if item.start <= index < item.end),
            None,
        )
        if section is None:
            raise SectionsError("Heading tidak berada di section mana pun")
        if section.start == index:
            continue
        add_section_break(package, before=heading, kind="nextPage")
        added += 1
    return added


class SectionsStage(BaseStage):
    """Bangun section break dan terapkan geometri halaman."""

    name = StageName.SECTIONS
    order = 50
    requires = canonical_prefix(StageName.SECTIONS)
    mutates = frozenset({DOCUMENT_PART})
    idempotent = True

    def enabled(self, ctx: object) -> bool:
        return not getattr(ctx, "dry_run", False)

    def run(self, ctx: object) -> StageResult:
        """Terapkan penomoran heading, section break, dan geometri halaman.

        Mengembalikan ``StageResult`` berisi metrik section dan heading.
        Melempar ``StageError`` bila package belum tersedia atau
        ``SectionError``/``HeadingError`` terjadi saat memutasi package.
        """

        started = time.monotonic()
        if not self.enabled(ctx):
            return StageResult(
                stage=self.name.value,
                status="skipped",
                changed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                warnings=("dry-run: stage sections tidak dijalankan.",),
            )
        package = getattr(ctx, "package", None)
        if package is None:
            raise StageError(
                self.name.value,
                "package DOCX belum tersedia; stage sections membutuhkan hasil Pandoc.",
                code="STAGE-PACKAGE",
            )
        before = _document_hash(package)
        try:
            sections_before = len(iter_sections(package))
            structure = getattr(ctx, "structure", None)
            body_titles = tuple(
                str(chapter.title) for chapter in getattr(structure, "body", ()) or ()
            )
            has_back_matter = bool(getattr(structure, "back_matter", ()))
            numbering = getattr(structure, "numbering", None)
            heading_report = None
            numbering_spec = None
            if numbering is not None:
                numbering_spec = NumberingSpec(
                    body=str(numbering.body),
                    sub_dot=bool(getattr(numbering, "sub_dot", True)),
                    subsub_dot=bool(getattr(numbering, "subsub_dot", True)),
                )
                heading_report = apply_heading_numbering(
                    package,
                    numbering_spec,
                    body_titles=body_titles,
                    has_back_matter=has_back_matter,
                )
            if numbering_spec is not None and package.has_part(NUMBERING_PART):
                toc_heading = getattr(getattr(ctx, "format", None), "toc_heading", None)
                try:
                    verify_heading_numbering(
                        package,
                        numbering_spec,
                        toc_heading_style=str(getattr(toc_heading, "heading_style", "TOCHeading")),
                    )
                except NumberingError as exc:
                    raise StageError(
                        self.name.value,
                        str(exc),
                        cause=exc,
                        code="STAGE-NUMBERING",
                    ) from exc
            added = _ensure_breaks(package, body_titles, has_back_matter)
            page = getattr(getattr(ctx, "format", None), "page", None)
            margin_sections = _apply_page_format(package, page)
            sections_after = len(iter_sections(package))
            for section in iter_sections(package):
                set_section_type(section, "nextPage")
        except (SectionError, HeadingError) as exc:
            raise StageError(
                self.name.value,
                str(exc),
                cause=exc,
                code=exc.code,
            ) from exc
        after = _document_hash(package)
        metrics: dict[str, int | str] = {
            "sections_before": sections_before,
            "sections_after": sections_after,
            "breaks_added": added,
            "margin_sections": margin_sections,
        }
        if heading_report is not None:
            metrics["headings_numbered"] = heading_report.numbered
            metrics["headings_unnumbered"] = heading_report.unnumbered
            metrics["headings_skipped"] = heading_report.skipped_without_chapter
        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=before != after,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics=metrics,
        )


__all__ = [
    "SectionsError",
    "SectionsStage",
]

"""Stage ``page_numbers``: Romawi untuk front matter, Arab untuk body.

Stage ini menulis ``w:pgNumType`` per section, membuat part header/footer
baru beserta relationship dan content type, lalu mengisi field ``PAGE``
native. Tidak ada probe tersembunyi untuk ``docx-pagenum``; Word/LibreOffice
yang mengisi nilai field saat dokumen dibuka.
"""

import time
from collections.abc import Mapping

from lxml import etree

from ..errors import StageError
from ..package.fields import FieldKind, FieldPosition, insert_field, iter_fields_in_part
from ..package.names import R_ID, W, local_name
from ..package.package import DOCUMENT_PART, DocumentPackage
from ..package.runs import copy_rpr
from ..package.sections import (
    HeaderFooterRefs,
    Section,
    SectionError,
    clear_header_footer_references,
    create_header_footer_part,
    header_footer_part,
    iter_sections,
    remove_unused_header_footer_parts,
    section_header_footer,
    set_header_footer_reference,
    set_page_number_format,
    set_part_xml,
    set_title_page,
)
from ..package.xml import sha256_c14n, tree_digest
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

FRONT_FOOTER_SIZE_HALF_POINTS = 24
BODY_HEADER_SIZE_HALF_POINTS = 20
BODY_FOOTER_SIZE_HALF_POINTS = 24

_FRONT_MATTER_KINDS = frozenset({"front_matter"})
_BODY_KINDS = frozenset({"body", "back_matter"})


def _root(kind: str) -> etree._Element:
    tag = "hdr" if kind == "header" else "ftr"
    return etree.Element(W + tag)


def _run_properties(
    *,
    hidden: bool,
    size_half_points: int,
) -> etree._Element:
    rpr = etree.Element(W + "rPr")
    if hidden:
        etree.SubElement(rpr, W + "vanish")
    if hidden:
        color = etree.SubElement(rpr, W + "color")
        color.set(W + "val", "FFFFFF")
    sz = etree.SubElement(rpr, W + "sz")
    sz.set(W + "val", str(size_half_points))
    sz_cs = etree.SubElement(rpr, W + "szCs")
    sz_cs.set(W + "val", str(size_half_points))
    return rpr


def page_part(
    kind: str,
    *,
    align: str,
    hidden: bool = False,
    size_half_points: int,
) -> etree._Element:
    """Buat root part header/footer berisi field PAGE native."""

    if kind not in ("header", "footer"):
        raise SectionError(f"Jenis part tidak dikenal: {kind!r}")
    if align not in ("left", "center", "right"):
        raise SectionError(f"Alignment halaman tidak dikenal: {align!r}")
    root = _root(kind)
    paragraph = etree.SubElement(root, W + "p")
    ppr = etree.SubElement(paragraph, W + "pPr")
    spacing = etree.SubElement(ppr, W + "spacing")
    spacing.set(W + "after", "0")
    spacing.set(W + "line", "240")
    spacing.set(W + "lineRule", "auto")
    indent = etree.SubElement(ppr, W + "ind")
    indent.set(W + "firstLine", "0")
    jc = etree.SubElement(ppr, W + "jc")
    jc.set(W + "val", align)
    rpr = _run_properties(
        hidden=hidden,
        size_half_points=size_half_points,
    )
    ppr.append(copy_rpr(rpr))
    insert_field(["PAGE"], FieldPosition(paragraph=paragraph, rpr=rpr), "1")
    return root


def empty_part(kind: str) -> etree._Element:
    """Part header/footer kosong untuk halaman pertama bab."""

    if kind not in ("header", "footer"):
        raise SectionError(f"Jenis part tidak dikenal: {kind!r}")
    root = _root(kind)
    etree.SubElement(root, W + "p")
    return root


def _default_footer_owners(
    package: DocumentPackage,
    *,
    body_titles: tuple[str, ...] = (),
) -> dict[str, frozenset[str]]:
    """Peta rel id footer default ke jenis section yang merujuknya.

    Pandoc dapat menulis satu part footer yang dipakai bersama oleh front
    matter dan body. Peta ini dipakai untuk memastikan part seperti itu tidak
    dipakai ulang untuk dua peran berbeda.
    """

    owners: dict[str, set[str]] = {}
    for section in iter_sections(package, body_titles=body_titles):
        rel_id = section_header_footer(section).footer
        if rel_id is not None:
            owners.setdefault(rel_id, set()).add(section.kind)
    return {rel_id: frozenset(kinds) for rel_id, kinds in owners.items()}


def _shared_footer_rel_id(
    owners: Mapping[str, frozenset[str]],
    allowed: frozenset[str],
) -> str | None:
    """Rel id footer pertama yang hanya dirujuk jenis section ``allowed``."""

    for rel_id, kinds in owners.items():
        if kinds <= allowed:
            return rel_id
    return None


def _safe_footer_rel_id(
    refs: HeaderFooterRefs,
    owners: Mapping[str, frozenset[str]],
    allowed: frozenset[str],
    fallback: str | None,
) -> str | None:
    """Pakai ``refs.footer`` hanya bila tidak dirujuk jenis section lain.

    ``fallback`` adalah part yang sudah dipakai section sejenis sebelumnya;
    ``None`` berarti pemanggil harus membuat part baru.
    """

    if refs.footer is not None and owners.get(refs.footer, frozenset()) <= allowed:
        return refs.footer
    return fallback


def _ensure_part(
    package: object,
    *,
    kind: str,
    rel_id: str | None,
    root: etree._Element,
) -> tuple[str, bool]:
    """Tulis part header/footer; buat relationship bila belum ada."""

    if rel_id is None:
        return (
            create_header_footer_part(package, kind=kind, content=root),  # type: ignore[arg-type]
            True,
        )
    part_name, current = header_footer_part(package, rel_id)
    if sha256_c14n(current) == sha256_c14n(root):
        return rel_id, False
    set_part_xml(package, part_name, root)
    return rel_id, True


def _configure_cover(section: Section) -> bool:
    before = tree_digest(section.sect_pr)
    clear_header_footer_references(section)
    for tag in ("pgNumType", "titlePg"):
        for element in list(section.sect_pr.findall(W + tag)):
            section.sect_pr.remove(element)
    return tree_digest(section.sect_pr) != before


def _configure_front_matter(
    package: object,
    section: Section,
    *,
    start: int | None,
    footer_rel_id: str | None,
) -> tuple[bool, str]:
    """Footer Romawi khusus front matter; mengembalikan rel id yang dipakai.

    ``footer_rel_id=None`` membuat part footer baru sehingga part body tidak
    pernah ditimpa oleh footer front matter.
    """

    before = tree_digest(section.sect_pr)
    footer_root = page_part(
        "footer",
        align="center",
        size_half_points=FRONT_FOOTER_SIZE_HALF_POINTS,
    )
    footer_id, part_changed = _ensure_part(
        package,
        kind="footer",
        rel_id=footer_rel_id,
        root=footer_root,
    )
    clear_header_footer_references(section)
    set_header_footer_reference(
        section,
        kind="footer",
        reference_type="default",
        rel_id=footer_id,
    )
    set_title_page(section, False)
    set_page_number_format(section, fmt="lowerRoman", start=start)
    return part_changed or tree_digest(section.sect_pr) != before, footer_id


def _configure_body(
    package: object,
    section: Section,
    *,
    start: int | None,
    footer_rel_id: str | None,
) -> tuple[bool, str]:
    """Konfigurasi header/footer dan format nomor untuk section body.

    ``footer_rel_id`` adalah part footer default tersembunyi yang dipakai
    bersama section body; ``None`` membuat part baru. Mengembalikan ``True``
    bila part header/footer atau ``sectPr`` berubah beserta rel id footer
    default yang dipakai. ``SectionError`` dari helper part diteruskan ke
    pemanggil.
    """

    before = tree_digest(section.sect_pr)
    refs = section_header_footer(section)

    header_root = page_part(
        "header",
        align="right",
        size_half_points=BODY_HEADER_SIZE_HALF_POINTS,
    )
    header_id, changed_header = _ensure_part(
        package, kind="header", rel_id=refs.header, root=header_root
    )
    first_header_root = empty_part("header")
    first_header_id, changed_first_header = _ensure_part(
        package,
        kind="header",
        rel_id=refs.first_page_header,
        root=first_header_root,
    )
    hidden_footer_root = page_part(
        "footer",
        align="center",
        hidden=True,
        size_half_points=BODY_FOOTER_SIZE_HALF_POINTS,
    )
    hidden_footer_id, changed_footer = _ensure_part(
        package,
        kind="footer",
        rel_id=footer_rel_id,
        root=hidden_footer_root,
    )
    first_footer_root = page_part(
        "footer",
        align="center",
        size_half_points=BODY_FOOTER_SIZE_HALF_POINTS,
    )
    first_footer_id, changed_first_footer = _ensure_part(
        package,
        kind="footer",
        rel_id=refs.first_page_footer,
        root=first_footer_root,
    )

    clear_header_footer_references(section)
    set_header_footer_reference(section, kind="header", reference_type="default", rel_id=header_id)
    set_header_footer_reference(
        section,
        kind="header",
        reference_type="first",
        rel_id=first_header_id,
    )
    set_header_footer_reference(
        section, kind="footer", reference_type="default", rel_id=hidden_footer_id
    )
    set_header_footer_reference(
        section,
        kind="footer",
        reference_type="first",
        rel_id=first_footer_id,
    )
    set_title_page(section, True)
    set_page_number_format(section, fmt="decimal", start=start)
    changed = (
        changed_header
        or changed_first_header
        or changed_footer
        or changed_first_footer
        or tree_digest(section.sect_pr) != before
    )
    return changed, hidden_footer_id


def _page_field_count(package: DocumentPackage) -> int:
    count = 0
    seen: set[str] = set()
    for section in iter_sections(package):
        for reference in section.sect_pr:
            if not isinstance(reference.tag, str):
                continue
            if local_name(reference.tag) not in (
                "headerReference",
                "footerReference",
            ):
                continue
            rel_id = reference.get(R_ID)
            if not rel_id or rel_id in seen:
                continue
            seen.add(rel_id)
            try:
                part_name, _root_element = header_footer_part(package, rel_id)
            except SectionError:
                continue
            fields = iter_fields_in_part(package, part_name)
            count += sum(1 for field in fields if field.kind is FieldKind.PAGE)
    return count


class PageNumbersStage(BaseStage):
    """Set format nomor halaman dan part header/footer per section."""

    name = StageName.PAGE_NUMBERS
    order = 140
    requires = canonical_prefix(StageName.PAGE_NUMBERS)
    mutates = frozenset(
        {
            DOCUMENT_PART,
            "word/header*.xml",
            "word/footer*.xml",
            "word/_rels/document.xml.rels",
            "[Content_Types].xml",
        }
    )
    idempotent = True

    def enabled(self, ctx: object) -> bool:
        return not getattr(ctx, "dry_run", False)

    def run(self, ctx: object) -> StageResult:
        """Konfigurasi nomor halaman untuk cover, front matter, dan body.

        Mengembalikan ``StageResult`` dengan metrik section dan field halaman.
        Melempar ``StageError`` bila package belum tersedia atau ``SectionError``
        terjadi saat memanipulasi section.
        """

        started = time.monotonic()
        if not self.enabled(ctx):
            return StageResult(
                stage=self.name.value,
                status="skipped",
                changed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                warnings=("dry-run: stage page_numbers tidak dijalankan.",),
            )
        package = getattr(ctx, "package", None)
        if package is None:
            raise StageError(
                self.name.value,
                "package DOCX belum tersedia; stage page_numbers membutuhkan hasil Pandoc.",
                code="STAGE-PACKAGE",
            )

        before_document = tree_digest(package.xml(DOCUMENT_PART))
        front_seen = 0
        body_seen = 0
        changed = False
        structure = getattr(ctx, "structure", None)
        body_titles = tuple(str(chapter.title) for chapter in getattr(structure, "body", ()) or ())
        sections = iter_sections(package, body_titles=body_titles)
        front_owners: dict[str, frozenset[str]] | None = None
        front_footer_id: str | None = None
        body_owners: dict[str, frozenset[str]] | None = None
        body_footer_id: str | None = None
        try:
            for section in sections:
                if section.kind == "cover":
                    changed = _configure_cover(section) or changed
                elif section.kind == "front_matter":
                    # Peta dihitung setelah cover dibersihkan agar reference
                    # cover tidak memaksa part footer baru.
                    if front_owners is None:
                        front_owners = _default_footer_owners(package, body_titles=body_titles)
                        front_footer_id = _shared_footer_rel_id(front_owners, _FRONT_MATTER_KINDS)
                    start = 1 if front_seen == 0 else None
                    section_changed, front_footer_id = _configure_front_matter(
                        package,
                        section,
                        start=start,
                        footer_rel_id=_safe_footer_rel_id(
                            section_header_footer(section),
                            front_owners,
                            _FRONT_MATTER_KINDS,
                            front_footer_id,
                        ),
                    )
                    changed = section_changed or changed
                    front_seen += 1
                else:
                    # Peta dihitung setelah front matter selesai agar footer
                    # miliknya tidak lagi terlihat sebagai milik body.
                    if body_owners is None:
                        body_owners = _default_footer_owners(package, body_titles=body_titles)
                        body_footer_id = _shared_footer_rel_id(body_owners, _BODY_KINDS)
                    start = 1 if body_seen == 0 else None
                    section_changed, body_footer_id = _configure_body(
                        package,
                        section,
                        start=start,
                        footer_rel_id=_safe_footer_rel_id(
                            section_header_footer(section),
                            body_owners,
                            _BODY_KINDS,
                            body_footer_id,
                        ),
                    )
                    changed = section_changed or changed
                    body_seen += 1
            if remove_unused_header_footer_parts(package):
                changed = True
        except SectionError as exc:
            raise StageError(
                self.name.value,
                str(exc),
                cause=exc,
                code=exc.code,
            ) from exc

        if tree_digest(package.xml(DOCUMENT_PART)) != before_document:
            changed = True
        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "sections": len(sections),
                "front_matter_sections": front_seen,
                "body_sections": body_seen,
                "page_fields": _page_field_count(package),
            },
        )


__all__ = [
    "BODY_FOOTER_SIZE_HALF_POINTS",
    "BODY_HEADER_SIZE_HALF_POINTS",
    "FRONT_FOOTER_SIZE_HALF_POINTS",
    "PageNumbersStage",
    "empty_part",
    "page_part",
]

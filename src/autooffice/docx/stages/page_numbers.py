"""Stage ``page_numbers``: Romawi untuk front matter, Arab untuk body.

Stage ini menulis ``w:pgNumType`` per section, membuat part header/footer
baru beserta relationship dan content type, lalu mengisi field ``PAGE``
native. Header body dapat memuat field ``STYLEREF`` untuk judul bab bila
``page.header_style_ref`` diisi. Tidak ada probe tersembunyi untuk
``docx-pagenum``; Word/LibreOffice yang mengisi nilai field saat dokumen
dibuka.
"""

import time

from lxml import etree

from ..config import PageFormat
from ..errors import StageError
from ..package.fields import FieldKind, FieldPosition, insert_field, iter_fields_in_part
from ..package.heading_numbering import is_unnumbered
from ..package.names import R_ID, W, local_name
from ..package.native_numbering import paragraph_numbering
from ..package.package import DOCUMENT_PART, DocumentPackage
from ..package.page import page_size
from ..package.paragraphs import (
    ParagraphError,
    body_children,
    document_body,
    heading_level,
)
from ..package.runs import build_run, copy_rpr
from ..package.sections import (
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
from ..package.styles import StyleError, resolve_style_name
from ..package.xml import sha256_c14n, tree_digest
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

FRONT_FOOTER_SIZE_HALF_POINTS = 24
BODY_HEADER_SIZE_HALF_POINTS = 20
BODY_FOOTER_SIZE_HALF_POINTS = 24


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


def _header_tab_position(page: PageFormat | None) -> int | None:
    """Posisi tab kanan header dari geometri ``PageFormat``, dalam twip.

    Nilai adalah lebar konten (lebar halaman dikurangi margin kiri/kanan dan
    gutter). ``None`` dikembalikan bila geometri tidak lengkap; header tetap
    ditulis tanpa tab stop eksplisit.
    """

    if page is None:
        return None
    try:
        width, _height = page_size(page.size, page.orientation)
        left = int(page.margins.left)
        right = int(page.margins.right)
        gutter = int(page.gutter)
    except AttributeError, KeyError, TypeError, ValueError:
        return None
    position = width - left - right - gutter
    return position if position > 0 else None


def _section_heading_starts_with_break(package: object, section: Section) -> bool:
    """True bila H1 pertama di section sudah membawa line break sebelum judul."""

    try:
        children = body_children(document_body(package))  # type: ignore[arg-type]
    except AttributeError, ParagraphError:
        return False
    for child in children[section.start : section.end]:
        if child.tag != W + "p" or heading_level(child) != 1:
            continue
        for node in child:
            if not isinstance(node.tag, str) or node.tag == W + "pPr":
                continue
            if node.tag == W + "br":
                return True
            if node.tag == W + "r":
                if node.find(W + "br") is not None:
                    return True
                if node.find(W + "t") is not None:
                    return False
            if node.tag in {
                W + "bookmarkStart",
                W + "bookmarkEnd",
                W + "proofErr",
                W + "commentRangeStart",
                W + "commentRangeEnd",
            }:
                continue
            return False
        return False
    return False


def body_header_part(
    *,
    style_name: str,
    tab_pos: int | None,
    size_half_points: int,
    title_break: bool = True,
) -> etree._Element:
    r"""Part header body berisi field ``STYLEREF`` dan field ``PAGE``.

    Dua field ``STYLEREF`` dipakai karena heading memakai numbering native
    Word:

    - ``STYLEREF "<style>" \n`` mengembalikan label nomor paragraf
      (``BAB II``); tanpa switch ini Word mengembalikan teks judul saja.
    - ``STYLEREF "<style>"`` mengembalikan teks judul. Teks heading H1
      diawali ``w:br`` (dari raw inline Markdown), sehingga hasilnya menjadi
      baris kedua header: nomor di baris pertama, judul di baris kedua.

    Kombinasi ini menghasilkan ``BAB II`` + baris baru + ``TINJAUAN
    PUSTAKA``, sama seperti header literal sebelumnya. ``\s`` tidak dipakai:
    pengukuran Word 16 menunjukkan ``\s`` hanya menghasilkan ``II`` tanpa
    ``BAB``, sedangkan ``\n`` menghasilkan ``BAB II`` utuh.

    ``w:dirty="true"`` pada ``fldChar begin`` membuat Word memperbarui hasil
    field saat membuka dokumen. ``PAGE`` tetap dipertahankan agar nomor
    halaman body tidak hilang. Bila ``tab_pos`` tersedia, nomor halaman
    diletakkan di tab kanan; tanpa geometri, header tetap rata kanan.
    """

    root = _root("header")
    paragraph = etree.SubElement(root, W + "p")
    ppr = etree.SubElement(paragraph, W + "pPr")
    if tab_pos is not None:
        tabs = etree.SubElement(ppr, W + "tabs")
        tab_stop = etree.SubElement(tabs, W + "tab")
        tab_stop.set(W + "val", "right")
        tab_stop.set(W + "pos", str(tab_pos))
    spacing = etree.SubElement(ppr, W + "spacing")
    spacing.set(W + "after", "0")
    spacing.set(W + "line", "240")
    spacing.set(W + "lineRule", "auto")
    indent = etree.SubElement(ppr, W + "ind")
    indent.set(W + "firstLine", "0")
    jc = etree.SubElement(ppr, W + "jc")
    jc.set(W + "val", "left" if tab_pos is not None else "right")
    rpr = _run_properties(
        hidden=False,
        size_half_points=size_half_points,
    )
    ppr.append(copy_rpr(rpr))
    insert_field(
        ["STYLEREF", f'"{style_name}"', "\\n"],
        FieldPosition(paragraph=paragraph, rpr=rpr),
        "",
        dirty=True,
    )
    if title_break:
        break_run = build_run(rpr=rpr)
        etree.SubElement(break_run, W + "br")
        paragraph.append(break_run)
    insert_field(
        ["STYLEREF", f'"{style_name}"'],
        FieldPosition(paragraph=paragraph, rpr=rpr),
        "",
        dirty=True,
    )
    tab_run = build_run(rpr=rpr)
    etree.SubElement(tab_run, W + "tab")
    paragraph.append(tab_run)
    insert_field(["PAGE"], FieldPosition(paragraph=paragraph, rpr=rpr), "1")
    return root


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
) -> bool:
    before = tree_digest(section.sect_pr)
    refs = section_header_footer(section)
    footer_root = page_part(
        "footer",
        align="center",
        size_half_points=FRONT_FOOTER_SIZE_HALF_POINTS,
    )
    footer_id, part_changed = _ensure_part(
        package,
        kind="footer",
        rel_id=refs.footer,
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
    return part_changed or tree_digest(section.sect_pr) != before


def _section_has_unnumbered_chapter(package: object, section: Section) -> bool:
    """True bila section memuat H1 bernomor 0/unnumbered.

    STYLEREF ``
    `` menghasilkan ``0`` untuk heading tanpa numbering. Section
    seperti itu memakai header PAGE-only agar header tidak pernah menampilkan
    "0"; detail ada di ADR 0015.
    """

    try:
        children = body_children(document_body(package))  # type: ignore[arg-type]
    except AttributeError, ParagraphError:
        return False
    for child in children[section.start : section.end]:
        if child.tag != W + "p" or heading_level(child) != 1:
            continue
        numbering = paragraph_numbering(child)
        if numbering is not None and numbering[1] == 0:
            return True
        if numbering is None and is_unnumbered(child):
            return True
    return False


def _configure_body(
    package: object,
    section: Section,
    *,
    start: int | None,
    header_style_ref: str | None = None,
    header_tab_pos: int | None = None,
) -> bool:
    """Konfigurasi header/footer dan format nomor untuk section body.

    Mengembalikan ``True`` bila part header/footer atau ``sectPr`` berubah.
    ``header_style_ref`` ``None`` mempertahankan header body tanpa judul bab;
    nilai berisi nama style menghasilkan field ``STYLEREF`` di header default.
    ``SectionError`` dari helper part diteruskan ke pemanggil.
    """

    before = tree_digest(section.sect_pr)
    refs = section_header_footer(section)

    if header_style_ref is None or _section_has_unnumbered_chapter(package, section):
        header_root = page_part(
            "header",
            align="right",
            size_half_points=BODY_HEADER_SIZE_HALF_POINTS,
        )
    else:
        header_root = body_header_part(
            style_name=header_style_ref,
            tab_pos=header_tab_pos,
            size_half_points=BODY_HEADER_SIZE_HALF_POINTS,
            title_break=not _section_heading_starts_with_break(package, section),
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
        rel_id=refs.footer,
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
    return (
        changed_header
        or changed_first_header
        or changed_footer
        or changed_first_footer
        or tree_digest(section.sect_pr) != before
    )


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
        page = getattr(getattr(ctx, "format", None), "page", None)
        requested_style = getattr(page, "header_style_ref", None)
        header_style_ref: str | None = None
        if requested_style:
            try:
                header_style_ref = resolve_style_name(
                    package,
                    str(requested_style),
                    paragraph_only=True,
                    heading_only=True,
                )
            except StyleError as exc:
                raise StageError(
                    self.name.value,
                    str(exc),
                    cause=exc,
                    code="STAGE-HEADER-STYLE",
                ) from exc
        header_tab_pos = _header_tab_position(page) if header_style_ref else None
        front_seen = 0
        body_seen = 0
        changed = False
        structure = getattr(ctx, "structure", None)
        body_titles = tuple(str(chapter.title) for chapter in getattr(structure, "body", ()) or ())
        sections = iter_sections(package, body_titles=body_titles)
        try:
            for section in sections:
                if section.kind == "cover":
                    changed = _configure_cover(section) or changed
                elif section.kind == "front_matter":
                    start = 1 if front_seen == 0 else None
                    changed = (
                        _configure_front_matter(
                            package,
                            section,
                            start=start,
                        )
                        or changed
                    )
                    front_seen += 1
                else:
                    start = 1 if body_seen == 0 else None
                    section_style = header_style_ref if section.kind == "body" else None
                    changed = (
                        _configure_body(
                            package,
                            section,
                            start=start,
                            header_style_ref=section_style,
                            header_tab_pos=header_tab_pos if section_style else None,
                        )
                        or changed
                    )
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
    "body_header_part",
    "empty_part",
    "page_part",
]

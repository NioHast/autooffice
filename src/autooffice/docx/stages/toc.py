"""Stage ``toc``: field TOC native di dalam ``w:sdt`` dan verifikasi style TOC.

Stage ini menulis field TOC kosong; Word/LibreOffice mengisi entri dan nomor
halaman saat dokumen dibuka. Style ``TOC1``..``TOC3`` sudah dibekukan di
``reference.docx`` sumber dan hanya diverifikasi terhadap geometri final.
Tidak ada cache nomor halaman statis dan tidak ada TOC ganda: field lama
diganti.
"""

import time

from lxml import etree

from ..errors import StageError
from ..package.fields import (
    FieldError,
    FieldKind,
    ensure_no_blank_page_after_toc,
    insert_toc,
    iter_fields,
)
from ..package.names import W
from ..package.package import DOCUMENT_PART, DocumentPackage
from ..package.page import PAGE_SIZES, page_size
from ..package.sections import SectionError, iter_sections
from ..package.styles import StyleError, get_style_element
from ..package.xml import tree_digest
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

TOC_TITLE = "DAFTAR ISI"
TOC_ENTRY_STYLE_IDS = ("TOC1", "TOC2", "TOC3")


class TocError(FieldError):
    """Style TOC atau penyisipan field TOC gagal."""

    default_code = "TOC"


def _twips(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def tab_position(
    package: DocumentPackage, *, fallback: tuple[int, int, int, int] | None = None
) -> int:
    """Posisi tab kanan TOC dari geometri section pertama.

    Lebar konten dihitung dari ``w:pgSz/@w:w`` dikurangi ``w:pgMar/@w:left``,
    ``@w:right``, dan ``@w:gutter``. ``w:gutter`` opsional dan dihitung 0 bila
    tidak ada. ``fallback`` berisi ``(width, left_margin, right_margin, _)``
    dalam twip dan hanya dipakai bila geometri section tidak lengkap. Tidak ada
    angka bawaan: geometri tidak lengkap tanpa fallback eksplisit menimbulkan
    ``TocError`` berkode ``TOC-TAB``, begitu pula posisi tab <= 1000 twip.
    """

    try:
        sections = iter_sections(package)
    except SectionError as exc:
        sections = ()
        section_error: SectionError | None = exc
    else:
        section_error = None

    if sections:
        sect_pr = sections[0].sect_pr
        pg_sz = sect_pr.find(W + "pgSz")
        pg_mar = sect_pr.find(W + "pgMar")
        width = _twips(pg_sz.get(W + "w")) if pg_sz is not None else None
        left = _twips(pg_mar.get(W + "left")) if pg_mar is not None else None
        right = _twips(pg_mar.get(W + "right")) if pg_mar is not None else None
        gutter = _twips(pg_mar.get(W + "gutter")) if pg_mar is not None else None
        if width is not None and left is not None and right is not None:
            position = width - left - right - (gutter or 0)
            if position <= 1000:
                raise TocError(
                    f"posisi tab TOC tidak valid: {position} twip",
                    code="TOC-TAB",
                )
            return position

    if fallback is not None:
        width, left, right, _unused = fallback
        position = width - left - right
        if position <= 1000:
            raise TocError(
                f"posisi tab TOC dari fallback tidak valid: {position} twip",
                code="TOC-TAB",
            )
        return position

    message = "geometri section pertama tidak lengkap untuk posisi tab TOC"
    if section_error is not None:
        raise TocError(message, code="TOC-TAB") from section_error
    raise TocError(message, code="TOC-TAB")


def _style_tabs(style: etree._Element) -> tuple[tuple[str | None, str | None, str | None], ...]:
    """Kembalikan ``(val, leader, pos)`` untuk setiap ``w:tab`` di ``w:pPr``."""

    ppr = style.find(W + "pPr")
    if ppr is None:
        return ()
    tabs = ppr.find(W + "tabs")
    if tabs is None:
        return ()
    return tuple(
        (tab.get(W + "val"), tab.get(W + "leader"), tab.get(W + "pos"))
        for tab in tabs.findall(W + "tab")
    )


def verify_toc_styles(package: DocumentPackage, *, tab_pos: int | None = None) -> None:
    """Pastikan ``TOC1``..``TOC3`` memuat tab kanan berleader dot pada posisi.

    Nilai sudah dibekukan di ``reference.docx`` sumber; stage ini hanya
    memeriksa. ``tab_pos`` ``None`` memakai geometri section pertama. Style
    yang hilang atau tab yang tidak cocok melempar :class:`TocError` berkode
    ``TOC-STYLE``.
    """

    position = tab_pos if tab_pos is not None else tab_position(package)
    for style_id in TOC_ENTRY_STYLE_IDS:
        try:
            style = get_style_element(package, style_id)
        except StyleError as exc:
            raise TocError(
                f"style '{style_id}' wajib ada di word/styles.xml dengan tab kanan "
                f"pada {position} twip",
                code="TOC-STYLE",
                key=style_id,
            ) from exc
        tabs = _style_tabs(style)
        matching = [tab for tab in tabs if tab[0] == "right" and tab[2] == str(position)]
        if not matching:
            actual = (
                ", ".join(f"{value}/{leader}/{pos}" for value, leader, pos in tabs) or "tidak ada"
            )
            raise TocError(
                f"style '{style_id}' tidak memiliki tab kanan pada {position} twip; "
                f"tab aktual: {actual}",
                code="TOC-STYLE",
                key=style_id,
            )
        if matching[0][1] != "dot":
            raise TocError(
                f"style '{style_id}' tab kanan pada {position} twip memakai leader "
                f"{matching[0][1]!r}, seharusnya 'dot'",
                code="TOC-STYLE",
                key=style_id,
            )


def _document_hash(package: object) -> str:
    return tree_digest(package.xml(DOCUMENT_PART))  # type: ignore[attr-defined]


def _toc_field_count(package: object) -> int:
    return sum(1 for field in iter_fields(package) if field.kind is FieldKind.TOC)


def format_tab_fallback(ctx: object) -> tuple[int, int, int, int] | None:
    """Geometri halaman dari ``ctx.format.page`` dalam twip, atau ``None``.

    Nilai kembali ``(width, left_margin, right_margin, 0)``; ``None`` bila
    format tidak tersedia, ukuran halaman tidak dikenal, atau margin tidak
    ada. Dipakai stage ``toc`` dan ``lists`` sebagai fallback saat geometri
    package tidak lengkap.
    """

    page = getattr(getattr(ctx, "format", None), "page", None)
    if page is None:
        return None
    size = str(getattr(page, "size", "A4"))
    if size not in PAGE_SIZES:
        return None
    width, _height = page_size(size, str(getattr(page, "orientation", "portrait")))
    margins = getattr(page, "margins", None)
    if margins is None:
        return None
    return (
        width,
        int(getattr(margins, "left", 0)),
        int(getattr(margins, "right", 0)),
        0,
    )


class TocStage(BaseStage):
    """Tulis field TOC native dan verifikasi style TOC yang dibekukan."""

    name = StageName.TOC
    order = 130
    requires = canonical_prefix(StageName.TOC)
    mutates = frozenset({DOCUMENT_PART})
    idempotent = True

    def enabled(self, ctx: object) -> bool:
        if getattr(ctx, "dry_run", False):
            return False
        structure = getattr(ctx, "structure", None)
        return bool(getattr(structure, "toc", False))

    def run(self, ctx: object) -> StageResult:
        """Tulis field TOC native, verifikasi style TOC, jaga halaman setelahnya.

        Mengembalikan ``StageResult`` berisi jumlah field TOC. Melempar
        ``StageError`` bila package belum tersedia, style TOC tidak sesuai, atau
        ``FieldError`` terjadi saat menyisipkan field.
        """

        started = time.monotonic()
        if not self.enabled(ctx):
            return StageResult(
                stage=self.name.value,
                status="skipped",
                changed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                warnings=("structure.toc bernilai false; field TOC tidak ditulis.",),
            )
        package = getattr(ctx, "package", None)
        if package is None:
            raise StageError(
                self.name.value,
                "package DOCX belum tersedia; stage toc membutuhkan hasil Pandoc.",
                code="STAGE-PACKAGE",
            )
        before_document = _document_hash(package)
        try:
            position = tab_position(package, fallback=format_tab_fallback(ctx))
            verify_toc_styles(package, tab_pos=position)
            insert_toc(package, title=TOC_TITLE)
            ensure_no_blank_page_after_toc(package)
        except FieldError as exc:
            raise StageError(
                self.name.value,
                str(exc),
                cause=exc,
                code=exc.code,
            ) from exc
        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=_document_hash(package) != before_document,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "toc_fields": _toc_field_count(package),
                "toc_styles": len(TOC_ENTRY_STYLE_IDS),
                "tab_pos": position,
            },
        )


__all__ = [
    "TOC_ENTRY_STYLE_IDS",
    "TOC_TITLE",
    "TocError",
    "TocStage",
    "format_tab_fallback",
    "tab_position",
    "verify_toc_styles",
]

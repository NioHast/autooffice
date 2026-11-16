r"""Stage ``lists``: daftar tabel/gambar native dan field ``SEQ`` caption.

Stage ini tidak menulis caption dari nol. Caption dan nomor bab sudah dibuat
oleh stage ``captions``; stage ini mengganti angka urutan terakhir menjadi
field ``SEQ`` agar Word dapat memperbarui daftar. Prefix bab literal
dipertahankan dan switch ``\s 1`` tetap dipakai: Word mereset counter ``SEQ``
pada heading level 1, dan heading kini memakai numbering native ``w:numPr``
(style ``Heading1``) sehingga level 1 tetap dikenali. Pengukuran Word 16 pada
contoh tesis: setelah field diperbarui, caption tetap ``Tabel 2.1``,
``Gambar 3.1``, dan ``Tabel 4.1`` (identik baseline). Style entri
``TableofFigures`` sudah dibekukan di ``reference.docx`` sumber dan hanya
diverifikasi: flush left dengan tab leader dot selebar konten. Semua field
daftar ditulis lewat :mod:`autooffice.docx.package.fields`.
"""

import re
import time
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from lxml import etree

from ..errors import StageError
from ..package.captions import CaptionKind, is_caption_paragraph
from ..package.fields import (
    FieldError,
    FieldKind,
    FieldPosition,
    ensure_no_blank_page_after_toc,
    field_instruction,
    insert_field,
    insert_toc,
    iter_fields_in_paragraph,
    iter_fields_in_root,
)
from ..package.names import (
    W_HYPERLINK,
    W_R,
    W_RPR,
    W_SDT,
    W_T,
    W_VAL,
    W,
)
from ..package.package import DOCUMENT_PART
from ..package.page import PageError, content_width
from ..package.paragraphs import (
    ParagraphError,
    document_body,
    paragraph_text,
    remove_direct_children,
)
from ..package.runs import build_run
from ..package.styles import StyleError, get_style_element
from ..package.xml import (
    iter_paragraphs,
    iter_runs,
    qn,
    tree_digest,
)
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix
from .toc import format_tab_fallback

if TYPE_CHECKING:  # pragma: no cover - hanya anotasi
    from ..package.package import DocumentPackage

CAPTION_LABEL_DEFAULTS = {"table": "Tabel", "figure": "Gambar"}
LIST_ENTRY_STYLE_ID = "TableofFigures"
LIST_TITLES = {
    "list_of_tables": ("tables", "DAFTAR TABEL"),
    "list_of_figures": ("figures", "DAFTAR GAMBAR"),
}
_CAPTION_NUMBER_RE = re.compile(
    r"^\s*(?P<label>{label})(?P<separator>[\s.:]*)"
    r"(?P<number>\d+(?:\.\d+)*)(?P<rest>\s+.*|$)",
    re.IGNORECASE,
)
_LIST_INSTRUCTION_RE = re.compile(r"\\c\b")
_SDT_ID_BASE = 1180696142


def _body(package: DocumentPackage) -> etree._Element:
    try:
        return document_body(package)
    except ParagraphError as exc:
        raise FieldError(str(exc)) from exc


def _list_toc_sdts(body: etree._Element) -> tuple[etree._Element, ...]:
    r"""SDT TOC daftar (``TOC \c``) yang menjadi child langsung ``w:body``."""

    found: list[etree._Element] = []
    for child in body:
        if not isinstance(child.tag, str) or child.tag != W_SDT:
            continue
        if any(
            field.kind is FieldKind.TOC
            and _LIST_INSTRUCTION_RE.search(field_instruction(field)) is not None
            for field in iter_fields_in_root(child)
        ):
            found.append(child)
    return tuple(found)


def _sdt_ancestor(element: etree._Element) -> etree._Element:
    node: etree._Element | None = element
    while node is not None:
        if node.tag == W_SDT:
            return node
        node = node.getparent()
    raise FieldError("Field TOC tidak berada di dalam w:sdt")


def _next_sdt_id(body: etree._Element) -> int:
    highest = 0
    for sdt in body.iter(W_SDT):
        properties = sdt.find(qn("w:sdtPr"))
        if properties is None:
            continue
        identifier = properties.find(qn("w:id"))
        if identifier is None:
            continue
        try:
            highest = max(highest, int(identifier.get(W_VAL) or "0"))
        except ValueError:
            continue
    return max(_SDT_ID_BASE, highest + 1)


def _set_sdt_id(sdt: etree._Element, value: int) -> None:
    properties = sdt.find(qn("w:sdtPr"))
    if properties is None:
        return
    identifier = properties.find(qn("w:id"))
    if identifier is not None:
        identifier.set(W_VAL, str(value))


def _list_requests(structure: object | None) -> tuple[tuple[str, str], ...]:
    """Daftar ``(kunci lists, judul)`` dari flag ``structure.lists``.

    Urutan field mengikuti baseline: daftar tabel sebelum daftar gambar.
    """

    if structure is None:
        return ()
    settings = getattr(structure, "lists", None)
    enabled = {
        "tables": bool(getattr(settings, "tables", False)),
        "figures": bool(getattr(settings, "figures", False)),
    }
    requests = (
        ("tables", LIST_TITLES["list_of_tables"][1]),
        ("figures", LIST_TITLES["list_of_figures"][1]),
    )
    return tuple(request for request in requests if enabled[request[0]])


def _caption_settings(format_value: object | None) -> dict[str, str]:
    captions = getattr(format_value, "captions", None)

    def label(kind: str) -> str:
        style = getattr(captions, kind, None)
        value = getattr(style, "label", None) if style is not None else None
        return str(value or CAPTION_LABEL_DEFAULTS[kind])

    return {
        "table": label("table"),
        "figure": label("figure"),
    }


def _caption_pattern(label: str) -> re.Pattern[str]:
    return re.compile(
        _CAPTION_NUMBER_RE.pattern.replace("{label}", re.escape(label)),
        re.IGNORECASE,
    )


def _caption_prefix(
    text: str,
    label: str,
) -> tuple[str, str, str, int, int] | None:
    """Pisahkan caption menjadi ``(before, counter, after, start, end)``.

    ``before`` mempertahankan label dan prefix bab literal; ``counter`` adalah
    angka yang akan diganti field ``SEQ``. ``start`` dan ``end`` adalah offset
    ``counter`` di dalam ``text``.
    """

    match = _caption_pattern(label).match(text)
    if match is None:
        return None
    number = match.group("number")
    start = match.start("number")
    if "." in number:
        head, _, _tail = number.rpartition(".")
        counter_start = start + len(head) + 1
        prefix = text[:counter_start]
        counter = text[counter_start : start + len(number)]
        after = text[start + len(number) :]
        return prefix, counter, after, counter_start, start + len(number)
    counter_start = start
    return (
        text[:counter_start],
        number,
        text[start + len(number) :],
        counter_start,
        start + len(number),
    )


def _run_text(run: etree._Element) -> str:
    return "".join(node.text or "" for node in run.iter(W_T))


def _caption_run_segments(
    paragraph: etree._Element,
    *,
    counter_start: int,
    counter_end: int,
) -> tuple[list[tuple[etree._Element | None, str]], list[tuple[etree._Element | None, str]]]:
    """Potong teks run caption menjadi bagian sebelum/sesudah nomor.

    ``w:rPr`` setiap run dipertahankan agar style karakter (mis.
    ``IstilahAsing``) pada teks caption tidak hilang saat nomor diganti field
    ``SEQ``.
    """

    before: list[tuple[etree._Element | None, str]] = []
    after: list[tuple[etree._Element | None, str]] = []
    offset = 0
    for run in iter_runs(paragraph):
        value = _run_text(run)
        if not value:
            continue
        run_start = offset
        run_end = offset + len(value)
        offset = run_end
        if run_end <= counter_start:
            before.append((run.find(W_RPR), value))
            continue
        if run_start >= counter_end:
            after.append((run.find(W_RPR), value))
            continue
        local_start = max(counter_start - run_start, 0)
        local_end = min(counter_end - run_start, len(value))
        if local_start > 0:
            before.append((run.find(W_RPR), value[:local_start]))
        if local_end < len(value):
            after.append((run.find(W_RPR), value[local_end:]))
    return before, after


def _ensure_caption_seq(
    paragraph: etree._Element,
    *,
    label: str,
) -> bool:
    """Ganti angka urutan caption dengan field ``SEQ`` bila belum ada."""

    if iter_fields_in_paragraph(paragraph):
        return False
    if paragraph.find(f".//{W_HYPERLINK}") is not None:
        return False

    text = paragraph_text(paragraph)
    parts = _caption_prefix(text, label)
    if parts is None:
        return False
    _before, counter, _after, counter_start, counter_end = parts

    before_runs, after_runs = _caption_run_segments(
        paragraph,
        counter_start=counter_start,
        counter_end=counter_end,
    )
    template_rpr = before_runs[-1][0] if before_runs else None
    remove_direct_children(paragraph, W_R)

    switches = ["SEQ", label, "\\*", "ARABIC", "\\s", "1"]

    for rpr, value in before_runs:
        paragraph.append(build_run(text=value, rpr=rpr))
    insert_field(
        switches,
        FieldPosition(paragraph=paragraph, rpr=template_rpr),
        counter,
    )
    for rpr, value in after_runs:
        paragraph.append(build_run(text=value, rpr=rpr))
    return True


def _ensure_caption_seq_fields(
    package: DocumentPackage,
    labels: dict[str, str],
) -> int:
    count = 0
    for paragraph in iter_paragraphs(_body(package)):
        if is_caption_paragraph(paragraph, CaptionKind.TABLE):
            if _ensure_caption_seq(
                paragraph,
                label=labels["table"],
            ):
                count += 1
            continue
        if is_caption_paragraph(paragraph, CaptionKind.FIGURE) and _ensure_caption_seq(
            paragraph,
            label=labels["figure"],
        ):
            count += 1
    return count


def _list_tab_position(package: DocumentPackage, ctx: object) -> int | None:
    """Posisi tab entri daftar dari geometri package atau format.

    Sumber pertama ``content_width(document_body(package))``. Bila section
    belum memiliki ``w:pgSz``/``w:pgMar`` lengkap, fallback memakai
    ``format_tab_fallback(ctx)`` dan menghitung ``width - left - right``.
    ``None`` hanya dikembalikan saat format halaman tidak tersedia/valid
    (mis. fixture sintetis tanpa ``format.page``).
    """

    try:
        return content_width(_body(package))
    except PageError:
        fallback = format_tab_fallback(ctx)
        if fallback is None:
            return None
        width, left, right, _unused = fallback
        return width - left - right


def _verify_style_attrs(
    element: etree._Element | None,
    *,
    style_id: str,
    label: str,
    expected: Mapping[str, str],
) -> None:
    """Pastikan atribut ``w:val``/lainnya pada ``element`` sesuai harapan."""

    if element is None:
        raise FieldError(
            f"style '{style_id}' tidak memiliki {label}",
            code="LIST-STYLE",
            key=style_id,
        )
    for name, value in expected.items():
        actual = element.get(W_VAL if name == "val" else W + name)
        if actual != value:
            raise FieldError(
                f"style '{style_id}': {label}@{name} bernilai {actual!r}, seharusnya {value!r}",
                code="LIST-STYLE",
                key=style_id,
            )


def verify_list_entry_style(package: DocumentPackage, *, tab_pos: int | None) -> None:
    """Pastikan ``TableofFigures`` sesuai nilai yang dibekukan di reference.

    Style wajib ada, bertipe paragraf, memakai indentasi nol, spacing
    ``before``/``after`` 0 dengan line 360, dan (bila ``tab_pos`` diketahui)
    satu tab kanan berleader dot pada posisi tersebut. Pelanggaran melempar
    :class:`FieldError` berkode ``LIST-STYLE``.
    """

    try:
        style = get_style_element(package, LIST_ENTRY_STYLE_ID)
    except StyleError as exc:
        raise FieldError(
            f"style '{LIST_ENTRY_STYLE_ID}' wajib ada di word/styles.xml",
            code="LIST-STYLE",
            key=LIST_ENTRY_STYLE_ID,
        ) from exc

    if style.get(W + "type") not in {None, "paragraph"}:
        raise FieldError(
            f"style '{LIST_ENTRY_STYLE_ID}' bertipe {style.get(W + 'type')!r}, "
            "seharusnya 'paragraph'",
            code="LIST-STYLE",
            key=LIST_ENTRY_STYLE_ID,
        )

    name = style.find(W + "name")
    _verify_style_attrs(
        name, style_id=LIST_ENTRY_STYLE_ID, label="w:name", expected={"val": "table of figures"}
    )
    based_on = style.find(W + "basedOn")
    _verify_style_attrs(
        based_on,
        style_id=LIST_ENTRY_STYLE_ID,
        label="w:basedOn",
        expected={"val": "Normal"},
    )
    next_style = style.find(W + "next")
    _verify_style_attrs(
        next_style,
        style_id=LIST_ENTRY_STYLE_ID,
        label="w:next",
        expected={"val": "Normal"},
    )

    ppr = style.find(W + "pPr")
    if ppr is None:
        raise FieldError(
            f"style '{LIST_ENTRY_STYLE_ID}' tidak memiliki w:pPr",
            code="LIST-STYLE",
            key=LIST_ENTRY_STYLE_ID,
        )
    _verify_style_attrs(
        ppr.find(W + "spacing"),
        style_id=LIST_ENTRY_STYLE_ID,
        label="w:spacing",
        expected={"before": "0", "after": "0", "line": "360", "lineRule": "auto"},
    )
    _verify_style_attrs(
        ppr.find(W + "ind"),
        style_id=LIST_ENTRY_STYLE_ID,
        label="w:ind",
        expected={"left": "0", "right": "0", "firstLine": "0"},
    )
    _verify_style_attrs(
        ppr.find(W + "jc"),
        style_id=LIST_ENTRY_STYLE_ID,
        label="w:jc",
        expected={"val": "left"},
    )

    if tab_pos is None:
        return
    tabs = ppr.find(W + "tabs")
    matching = (
        ()
        if tabs is None
        else tuple(
            tab
            for tab in tabs.findall(W + "tab")
            if tab.get(W_VAL) == "right" and tab.get(W + "pos") == str(tab_pos)
        )
    )
    if not matching:
        raise FieldError(
            f"style '{LIST_ENTRY_STYLE_ID}' tidak memiliki tab kanan pada {tab_pos} twip",
            code="LIST-STYLE",
            key=LIST_ENTRY_STYLE_ID,
        )
    if matching[0].get(W + "leader") != "dot":
        raise FieldError(
            f"style '{LIST_ENTRY_STYLE_ID}' tab kanan pada {tab_pos} twip memakai "
            f"leader {matching[0].get(W + 'leader')!r}, seharusnya 'dot'",
            code="LIST-STYLE",
            key=LIST_ENTRY_STYLE_ID,
        )


def _insert_list_fields(
    package: DocumentPackage,
    requests: Sequence[tuple[str, str]],
    labels: dict[str, str],
    *,
    tab_pos: int | None,
) -> int:
    """Tulis semua field daftar tanpa menghapus TOC utama yang sudah ada."""

    body = _body(package)
    for sdt in _list_toc_sdts(body):
        parent = sdt.getparent()
        if parent is not None:
            parent.remove(sdt)

    verify_list_entry_style(package, tab_pos=tab_pos)

    next_id = _next_sdt_id(body)
    for index, (key, title) in enumerate(requests):
        caption_label = labels["table" if key == "tables" else "figure"]
        field = insert_toc(
            package,
            title=title,
            caption=caption_label,
            keep_existing=True,
            page_break_before=True,
        )
        _set_sdt_id(_sdt_ancestor(field.begin), next_id + index)

    ensure_no_blank_page_after_toc(package)
    return len(requests)


class ListsStage(BaseStage):
    """Tulis daftar tabel/gambar dan field ``SEQ`` pada caption."""

    name = StageName.LISTS
    # stage-api v0.12: page_numbers (140) -> lists (150).
    order = 150
    requires = canonical_prefix(StageName.LISTS)
    mutates = frozenset({DOCUMENT_PART})
    idempotent = True

    def enabled(self, ctx: object) -> bool:
        if getattr(ctx, "dry_run", False):
            return False
        return bool(_list_requests(getattr(ctx, "structure", None)))

    def run(self, ctx: object) -> StageResult:
        """Tulis field daftar tabel/gambar dan field ``SEQ`` pada caption.

        Mengembalikan ``StageResult`` dengan jumlah field yang dibuat. Melempar
        ``StageError`` bila package belum tersedia atau ``FieldError`` terjadi.
        """

        started = time.monotonic()
        if not self.enabled(ctx):
            return StageResult(
                stage=self.name.value,
                status="skipped",
                changed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                warnings=(
                    "Tidak ada daftar tabel/gambar di structure.front_matter atau build dry-run.",
                ),
            )
        requests = _list_requests(getattr(ctx, "structure", None))
        package = getattr(ctx, "package", None)
        if package is None:
            raise StageError(
                self.name.value,
                "package DOCX belum tersedia; stage lists membutuhkan hasil Pandoc.",
                code="STAGE-PACKAGE",
            )

        before_document = tree_digest(package.xml(DOCUMENT_PART))
        labels = _caption_settings(getattr(ctx, "format", None))
        try:
            tab_pos = _list_tab_position(package, ctx)
            seq_fields = _ensure_caption_seq_fields(package, labels)
            list_fields = _insert_list_fields(
                package,
                requests,
                labels,
                tab_pos=tab_pos,
            )
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
            changed=tree_digest(package.xml(DOCUMENT_PART)) != before_document,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "list_fields": list_fields,
                "seq_fields": seq_fields,
                "list_styles": 1,
            },
        )


__all__ = [
    "CAPTION_LABEL_DEFAULTS",
    "LIST_ENTRY_STYLE_ID",
    "LIST_TITLES",
    "ListsStage",
    "_list_requests",
    "verify_list_entry_style",
]

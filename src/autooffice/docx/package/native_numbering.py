"""Numbering native Word untuk heading DOCX.

Modul ini menulis definisi numbering ke ``word/numbering.xml`` dan memasang
``w:numPr`` pada style ``Heading1``..``Heading3`` di ``word/styles.xml``.
Word kemudian menghasilkan label bab/subbab sebagai list label, bukan teks
paragraf. Nomor heading tidak lagi ditulis sebagai run oleh pipeline.

Id numbering **dialokasikan dinamis** dari rentang yang masih bebas:
``abstractNumId`` < 990 dan ``numId`` < 1000. Pandoc membuang entri reference
di luar batas itu (``Text.Pandoc.Writers.Docx.mkNumberingEntry``), sedangkan
reference stok Pandoc memakai 990/1000 untuk bullet. Id yang sudah dipakai
list lain tidak pernah ditimpa; bila tidak ada id bebas, build gagal.

Definisi level mengikuti ``structure.numbering``:

- ``BAB_ROMAN``: level 1 ``upperRoman``, ``BAB %1``;
- ``ARABIC_DOTTED``: level 1 ``decimal``, ``%1.``;
- level 2/3 memakai ``decimal`` dengan ``w:isLgl`` agar ``%1`` tampil desimal.

Semua heading memakai satu ``numId`` agar level 2/3 restart per bab. Label
level 1 tidak diikuti separator (``w:suff=nothing``) karena pipeline menaruh
``w:br`` di awal teks judul agar nomor dan judul tetap dua baris seperti
baseline.
"""

from dataclasses import dataclass

from lxml import etree

from . import DocxError
from .names import W, local_name
from .package import DOCUMENT_PART, DocumentPackage, Relationship
from .styles import StyleError, set_style_numbering, style_numbering
from .xml import LVL_ORDER, PPR_ORDER, insert_ordered, sha256_c14n

NUMBERING_PART = "word/numbering.xml"
NUMBERING_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"
)
REL_TYPE_NUMBERING = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering"

# Pandoc keeps reference numbering only below these limits.
MAX_ABSTRACT_NUM_ID = 989
MAX_NUM_ID = 999

HEADING_LEVELS = (1, 2, 3)
HEADING_STYLE_IDS = tuple(f"Heading{level}" for level in HEADING_LEVELS)
DEFAULT_TOC_HEADING_STYLE_ID = "TOCHeading"

# Penanda internal agar definisi heading milik AutoOffice dapat dikenali saat
# rebuild tanpa menebak dari id atau properti style.
_NSID = "0A0015A0"
_TMPL = "0A0015A0"
_LEVEL_INDENT = 709
_LEVEL_TAB = 720


class NumberingError(DocxError):
    """Numbering native tidak lengkap, bertabrakan, atau tidak konsisten."""

    default_code = "STYLE-NUMBERING"


@dataclass(frozen=True)
class NumberingSpec:
    """Konfigurasi penomoran heading dari ``structure.numbering``."""

    body: str = "BAB_ROMAN"
    sub_dot: bool = True
    subsub_dot: bool = True

    def __post_init__(self) -> None:
        if self.body not in ("BAB_ROMAN", "ARABIC_DOTTED"):
            raise NumberingError(f"format penomoran body tidak dikenal: {self.body!r}")


def _level_text(spec: NumberingSpec, level: int) -> tuple[str, str, str, bool]:
    """``(numFmt, lvlText, suff, isLgl)`` untuk level 1-based."""

    if level == 1:
        if spec.body == "BAB_ROMAN":
            return ("upperRoman", "BAB %1", "nothing", False)
        return ("decimal", "%1.", "space", False)
    if level == 2:
        suffix = "." if spec.sub_dot else ""
        return ("decimal", f"%1.%2{suffix}", "tab", True)
    suffix = "." if spec.subsub_dot else ""
    return ("decimal", f"%1.%2.%3{suffix}", "tab", True)


def _ordered_child(parent: etree._Element, tag: str) -> etree._Element:
    child = etree.Element(W + tag)
    insert_ordered(parent, child, LVL_ORDER)
    return child


def _level_element(spec: NumberingSpec, level: int) -> etree._Element:
    num_fmt, level_text, suffix, is_lgl = _level_text(spec, level)
    element = etree.Element(W + "lvl")
    element.set(W + "ilvl", str(level - 1))
    start = _ordered_child(element, "start")
    start.set(W + "val", "1")
    fmt = _ordered_child(element, "numFmt")
    fmt.set(W + "val", num_fmt)
    style = _ordered_child(element, "pStyle")
    style.set(W + "val", f"Heading{level}")
    if is_lgl:
        _ordered_child(element, "isLgl")
    suff = _ordered_child(element, "suff")
    suff.set(W + "val", suffix)
    text = _ordered_child(element, "lvlText")
    text.set(W + "val", level_text)
    jc = _ordered_child(element, "lvlJc")
    jc.set(W + "val", "left")
    ppr = _ordered_child(element, "pPr")
    tabs = etree.SubElement(ppr, W + "tabs")
    tab = etree.SubElement(tabs, W + "tab")
    tab.set(W + "val", "num")
    tab.set(W + "pos", "0" if level == 1 else str(_LEVEL_TAB))
    ind = etree.SubElement(ppr, W + "ind")
    if level == 1:
        ind.set(W + "left", "0")
        ind.set(W + "firstLine", "0")
    else:
        ind.set(W + "left", str(_LEVEL_INDENT))
        ind.set(W + "hanging", str(_LEVEL_INDENT))
    return element


def _abstract_num_element(spec: NumberingSpec, abstract_id: int) -> etree._Element:
    abstract = etree.Element(W + "abstractNum")
    abstract.set(W + "abstractNumId", str(abstract_id))
    nsid = etree.SubElement(abstract, W + "nsid")
    nsid.set(W + "val", _NSID)
    multi = etree.SubElement(abstract, W + "multiLevelType")
    multi.set(W + "val", "multilevel")
    template = etree.SubElement(abstract, W + "tmpl")
    template.set(W + "val", _TMPL)
    for level in HEADING_LEVELS:
        abstract.append(_level_element(spec, level))
    return abstract


def _num_element(num_id: int, abstract_id: int) -> etree._Element:
    element = etree.Element(W + "num")
    element.set(W + "numId", str(num_id))
    abstract = etree.SubElement(element, W + "abstractNumId")
    abstract.set(W + "val", str(abstract_id))
    return element


def _numbering_root(package: DocumentPackage) -> etree._Element:
    if package.has_part(NUMBERING_PART):
        root = package.xml(NUMBERING_PART)
        if root.tag != W + "numbering":
            raise NumberingError(
                "root word/numbering.xml bukan w:numbering",
                code="STYLE-NUMBERING",
            )
        return root
    return etree.Element(W + "numbering", nsmap={"w": W[1:-1]})


def _ours_abstract(root: etree._Element) -> etree._Element | None:
    for abstract in root.findall(W + "abstractNum"):
        nsid = abstract.find(W + "nsid")
        if nsid is not None and nsid.get(W + "val") == _NSID:
            return abstract
    return None


def _abstract_ids(root: etree._Element) -> set[int]:
    result: set[int] = set()
    for abstract in root.findall(W + "abstractNum"):
        value = abstract.get(W + "abstractNumId")
        if value is not None and value.isdigit():
            result.add(int(value))
    return result


def _num_ids(root: etree._Element) -> set[int]:
    result: set[int] = set()
    for num in root.findall(W + "num"):
        value = num.get(W + "numId")
        if value is not None and value.isdigit():
            result.add(int(value))
    return result


def _abstract_id_of(num: etree._Element) -> int | None:
    abstract = num.find(W + "abstractNumId")
    if abstract is None:
        return None
    value = abstract.get(W + "val")
    return int(value) if value is not None and value.isdigit() else None


def _remove_our_definitions(root: etree._Element) -> tuple[int, ...]:
    """Hapus abstract milik kita dan semua num yang menunjuknya."""

    abstract = _ours_abstract(root)
    if abstract is None:
        return ()
    abstract_id = abstract.get(W + "abstractNumId")
    root.remove(abstract)
    removed_nums: list[int] = []
    for num in list(root.findall(W + "num")):
        if abstract_id is None or _abstract_id_of(num) != int(abstract_id):
            continue
        value = num.get(W + "numId")
        if value is not None and value.isdigit():
            removed_nums.append(int(value))
        root.remove(num)
    return tuple(removed_nums)


def _allocate_ids(root: etree._Element) -> tuple[int, int]:
    """Pilih ``(num_id, abstract_id)`` bebas tertinggi di bawah batas Pandoc."""

    used_abstract = _abstract_ids(root)
    used_num = _num_ids(root)
    abstract_id = next(
        (
            candidate
            for candidate in range(MAX_ABSTRACT_NUM_ID, 0, -1)
            if candidate not in used_abstract
        ),
        None,
    )
    num_id = next(
        (candidate for candidate in range(MAX_NUM_ID, 0, -1) if candidate not in used_num),
        None,
    )
    if abstract_id is None or num_id is None:
        raise NumberingError(
            "tidak ada abstractNumId < 990 / numId < 1000 yang bebas untuk "
            "numbering heading; reference tidak dapat ditimpa",
            code="STYLE-NUMBERING",
        )
    return num_id, abstract_id


def _existing_heading_numbering(
    package: DocumentPackage,
) -> tuple[int, int] | None:
    """Id numbering heading milik kita yang sudah terpasang, bila ada."""

    binding = style_numbering(package, "Heading1")
    if binding is None or binding[1] in (None, 0):
        return None
    num_id = binding[1]
    root = _numbering_root(package)
    for num in root.findall(W + "num"):
        if num.get(W + "numId") != str(num_id):
            continue
        abstract_id = _abstract_id_of(num)
        if abstract_id is None:
            return None
        for abstract in root.findall(W + "abstractNum"):
            if abstract.get(W + "abstractNumId") != str(abstract_id):
                continue
            nsid = abstract.find(W + "nsid")
            if nsid is not None and nsid.get(W + "val") == _NSID:
                return num_id, abstract_id
            raise NumberingError(
                f"reference sudah memakai numbering heading lain pada "
                f"numId={num_id}; definisi tidak ditimpa",
                code="STYLE-NUMBERING",
            )
    return None


def _insert_abstract(root: etree._Element, abstract: etree._Element) -> None:
    abstracts = root.findall(W + "abstractNum")
    if abstracts:
        abstracts[-1].addnext(abstract)
        return
    first_num = root.find(W + "num")
    if first_num is not None:
        root.insert(root.index(first_num), abstract)
        return
    root.insert(0, abstract)


def _ensure_relationship(package: DocumentPackage) -> bool:
    relationships = package.relationships(DOCUMENT_PART)
    for relationship in relationships:
        if relationship.rel_type == REL_TYPE_NUMBERING:
            return False
    used = {relationship.rel_id for relationship in relationships}
    index = 1
    while f"rId{index}" in used:
        index += 1
    package.add_relationship(
        DOCUMENT_PART,
        Relationship(
            rel_id=f"rId{index}",
            rel_type=REL_TYPE_NUMBERING,
            target="numbering.xml",
        ),
    )
    return True


def ensure_heading_numbering(
    package: DocumentPackage,
    spec: NumberingSpec | None = None,
    *,
    toc_heading_style: str = DEFAULT_TOC_HEADING_STYLE_ID,
) -> bool:
    """Tulis definisi numbering dan ``w:numPr`` pada style Heading1..3.

    ``toc_heading_style`` diambil dari ``format.toc_heading.heading_style``.
    Mengembalikan ``True`` bila part, relationship, content type, atau style
    berubah. Idempoten: pemanggilan kedua dengan spec yang sama tidak menulis
    apa pun dan tidak mengganti id.
    """

    spec = spec or NumberingSpec()
    if not isinstance(toc_heading_style, str) or not toc_heading_style.strip():
        raise NumberingError("style TOCHeading tidak valid")
    changed = False
    created = not package.has_part(NUMBERING_PART)
    root = _numbering_root(package)
    before = sha256_c14n(root)

    existing = _existing_heading_numbering(package)
    reused_nums = _remove_our_definitions(root)
    num_id: int
    abstract_id: int | None
    if existing is not None:
        num_id, abstract_id = existing
    elif reused_nums:
        # Definsi kita ada tetapi tidak terhubung ke Heading1; pakai id lama
        # yang baru saja dibebaskan agar rebuild tetap stabil.
        abstract_id = next(
            (
                candidate
                for candidate in range(MAX_ABSTRACT_NUM_ID, 0, -1)
                if candidate not in _abstract_ids(root)
            ),
            None,
        )
        num_id = reused_nums[0]
        if abstract_id is None:
            raise NumberingError(
                "tidak ada abstractNumId < 990 yang bebas untuk numbering heading",
                code="STYLE-NUMBERING",
            )
    else:
        num_id, abstract_id = _allocate_ids(root)

    _insert_abstract(root, _abstract_num_element(spec, abstract_id))
    root.append(_num_element(num_id, abstract_id))
    if created:
        package.set_part(
            NUMBERING_PART,
            etree.tostring(
                root,
                xml_declaration=True,
                encoding="UTF-8",
                standalone=True,
            ),
            content_type=NUMBERING_CONTENT_TYPE,
        )
        changed = True
    else:
        if before != sha256_c14n(root):
            package.set_xml(NUMBERING_PART, root)
            changed = True
        previous_type = package.part_info(NUMBERING_PART).content_type
        package.ensure_content_type(NUMBERING_PART, NUMBERING_CONTENT_TYPE)
        if package.part_info(NUMBERING_PART).content_type != previous_type:
            changed = True
    if _ensure_relationship(package):
        changed = True

    for level in HEADING_LEVELS:
        try:
            if set_style_numbering(
                package,
                f"Heading{level}",
                num_id=num_id,
                level=level - 1,
            ):
                changed = True
        except StyleError as exc:  # pragma: no cover - reference selalu punya style
            raise NumberingError(str(exc), code=exc.code) from exc
    try:
        if set_style_numbering(package, toc_heading_style, num_id=0):
            changed = True
    except StyleError as exc:  # pragma: no cover - reference selalu punya style
        raise NumberingError(str(exc), code=exc.code) from exc
    return changed


def _level_text_matches(element: etree._Element, spec: NumberingSpec, level: int) -> bool:
    expected_fmt, expected_text, expected_suff, expected_lgl = _level_text(spec, level)
    fmt = element.find(W + "numFmt")
    text = element.find(W + "lvlText")
    suff = element.find(W + "suff")
    is_lgl = element.find(W + "isLgl")
    return (
        fmt is not None
        and fmt.get(W + "val") == expected_fmt
        and suff is not None
        and suff.get(W + "val") == expected_suff
        and text is not None
        and text.get(W + "val") == expected_text
        and (is_lgl is not None) == expected_lgl
    )


def verify_heading_numbering(
    package: DocumentPackage,
    spec: NumberingSpec | None = None,
    *,
    toc_heading_style: str = DEFAULT_TOC_HEADING_STYLE_ID,
) -> None:
    """Verifikasi numbering part, plumbing, style, dan kepemilikan id.

    Dapat dipanggil pada reference turunan maupun output setelah Pandoc. Bila
    ada ``w:num`` lain yang menunjuk abstract heading, verifikasi gagal agar
    list pengguna tidak berubah menjadi heading tanpa terlihat.
    """

    spec = spec or NumberingSpec()
    if not package.has_part(NUMBERING_PART):
        raise NumberingError(
            "word/numbering.xml tidak ada di package",
            code="STYLE-NUMBERING",
        )
    content_type = package.part_info(NUMBERING_PART).content_type
    if content_type != NUMBERING_CONTENT_TYPE:
        raise NumberingError(
            f"content type numbering tidak sesuai: {content_type!r}",
            code="STYLE-NUMBERING",
        )
    if not any(
        relationship.rel_type == REL_TYPE_NUMBERING
        for relationship in package.relationships(DOCUMENT_PART)
    ):
        raise NumberingError(
            "document.xml tidak memiliki relationship ke numbering.xml",
            code="STYLE-NUMBERING",
        )

    binding = style_numbering(package, "Heading1")
    if binding is None or binding[1] in (None, 0):
        raise NumberingError(
            "style Heading1 tidak memiliki numPr numbering heading",
            code="STYLE-NUMBERING",
        )
    num_id = binding[1]
    for level in HEADING_LEVELS:
        expected = (level - 1, num_id)
        if style_numbering(package, f"Heading{level}") != expected:
            raise NumberingError(
                f"style Heading{level} tidak memiliki numPr {expected}",
                code="STYLE-NUMBERING",
            )

    root = package.xml(NUMBERING_PART)
    nums = [
        element for element in root.findall(W + "num") if element.get(W + "numId") == str(num_id)
    ]
    if len(nums) != 1:
        raise NumberingError(
            f"numId {num_id} harus tepat satu",
            code="STYLE-NUMBERING",
        )
    abstract_id = _abstract_id_of(nums[0])
    if abstract_id is None:
        raise NumberingError(
            f"numId {num_id} tidak menunjuk abstractNum",
            code="STYLE-NUMBERING",
        )
    for num in root.findall(W + "num"):
        if num is nums[0]:
            continue
        if _abstract_id_of(num) == abstract_id:
            raise NumberingError(
                f"w:num {num.get(W + 'numId')} juga menunjuk abstractNum heading "
                f"{abstract_id}; definisi akan mengubah list itu",
                code="STYLE-NUMBERING",
            )

    abstracts = [
        element
        for element in root.findall(W + "abstractNum")
        if element.get(W + "abstractNumId") == str(abstract_id)
    ]
    if len(abstracts) != 1:
        raise NumberingError(
            f"abstractNum {abstract_id} harus tepat satu",
            code="STYLE-NUMBERING",
        )
    levels = {level.get(W + "ilvl"): level for level in abstracts[0].findall(W + "lvl")}
    for level in HEADING_LEVELS:
        element = levels.get(str(level - 1))
        if element is None:
            raise NumberingError(
                f"level numbering {level} tidak ada",
                code="STYLE-NUMBERING",
            )
        style = element.find(W + "pStyle")
        if style is None or style.get(W + "val") != f"Heading{level}":
            raise NumberingError(
                f"level numbering {level} tidak menunjuk Heading{level}",
                code="STYLE-NUMBERING",
            )
        if not _level_text_matches(element, spec, level):
            raise NumberingError(
                f"definisi numbering level {level} tidak sesuai structure.numbering",
                code="STYLE-NUMBERING",
            )
    if style_numbering(package, toc_heading_style) != (None, 0):
        raise NumberingError(
            f"style {toc_heading_style} harus memiliki numId=0",
            code="STYLE-NUMBERING",
        )


def set_paragraph_unnumbered(paragraph: etree._Element) -> bool:
    """Pasang override ``w:numPr`` dengan ``numId=0`` pada paragraf heading.

    ``numId=0`` berarti tanpa numbering; ini satu-satunya cara mematikan
    numbering level style untuk heading tak bernomor (LAMPIRAN, DAFTAR
    PUSTAKA, subbab adendum). Mengembalikan ``True`` bila XML berubah.
    """

    ppr = paragraph.find(W + "pPr")
    if ppr is None:
        ppr = etree.Element(W + "pPr")
        paragraph.insert(0, ppr)
    num_pr = ppr.find(W + "numPr")
    if num_pr is None:
        num_pr = etree.Element(W + "numPr")
        num_index = PPR_ORDER.index("numPr")
        insert_at = len(ppr)
        for index, child in enumerate(ppr):
            if not isinstance(child.tag, str):
                continue
            name = local_name(child.tag)
            if name in PPR_ORDER and PPR_ORDER.index(name) > num_index:
                insert_at = index
                break
        ppr.insert(insert_at, num_pr)
    before = sha256_c14n(num_pr)
    for child in list(num_pr):
        if isinstance(child.tag, str):
            num_pr.remove(child)
    identifier = etree.SubElement(num_pr, W + "numId")
    identifier.set(W + "val", "0")
    return before != sha256_c14n(num_pr)


def paragraph_numbering(paragraph: etree._Element) -> tuple[int | None, int | None] | None:
    """``(level, numId)`` override langsung paragraf, atau ``None``."""

    ppr = paragraph.find(W + "pPr")
    if ppr is None:
        return None
    num_pr = ppr.find(W + "numPr")
    if num_pr is None:
        return None
    ilvl = num_pr.find(W + "ilvl")
    num_element = num_pr.find(W + "numId")
    level = None
    if ilvl is not None and ilvl.get(W + "val") is not None:
        level = int(ilvl.get(W + "val"))
    num_id = None
    if num_element is not None and num_element.get(W + "val") is not None:
        num_id = int(num_element.get(W + "val"))
    return level, num_id


__all__ = [
    "DEFAULT_TOC_HEADING_STYLE_ID",
    "HEADING_LEVELS",
    "HEADING_STYLE_IDS",
    "MAX_ABSTRACT_NUM_ID",
    "MAX_NUM_ID",
    "NUMBERING_CONTENT_TYPE",
    "NUMBERING_PART",
    "REL_TYPE_NUMBERING",
    "NumberingError",
    "NumberingSpec",
    "ensure_heading_numbering",
    "paragraph_numbering",
    "set_paragraph_unnumbered",
    "verify_heading_numbering",
]

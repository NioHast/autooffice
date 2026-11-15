"""Tes unit nomor halaman Romawi/Arab dan stage ``page_numbers``."""

import html
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from autooffice.docx.errors import StageError
from autooffice.docx.package.fields import (
    FieldKind,
    field_instruction,
    iter_fields_in_part,
)
from autooffice.docx.package.heading_numbering import NumberingSpec, apply_heading_numbering
from autooffice.docx.package.package import (
    CONTENT_TYPES_PART,
    DOCUMENT_PART,
    PACKAGE_RELS_PART,
    REL_TYPE_OFFICE_DOCUMENT,
    REL_TYPE_STYLES,
    DocumentPackage,
)
from autooffice.docx.package.sections import (
    header_footer_part,
    iter_sections,
    section_header_footer,
)
from autooffice.docx.package.xml import qn, sha256_c14n
from autooffice.docx.pipeline import StageName
from autooffice.docx.stages.page_numbers import (
    BODY_HEADER_SIZE_HALF_POINTS,
    PageNumbersStage,
    page_part,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "fixtures" / "golden" / "laporan-baseline.docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

RELS_CONTENT_TYPE = "application/vnd.openxmlformats-package.relationships+xml"
DOCUMENT_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
STYLES_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"

STYLES_XML = (
    f'<w:styles xmlns:w="{W_NS}">'
    '<w:style w:type="paragraph" w:styleId="Normal">'
    '<w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1">'
    '<w:name w:val="heading 1"/>'
    '<w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Plain">'
    '<w:name w:val="Plain"/></w:style>'
    '<w:style w:type="character" w:styleId="VerbatimChar">'
    '<w:name w:val="Verbatim Char"/></w:style>'
    "</w:styles>"
).encode()


# ---------------------------------------------------------------------------
# Helper package minimal
# ---------------------------------------------------------------------------


def _content_types() -> bytes:
    return (
        f'<Types xmlns="{CT_NS}">'
        f'<Default Extension="rels" ContentType="{RELS_CONTENT_TYPE}"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/{DOCUMENT_PART}" '
        f'ContentType="{DOCUMENT_CONTENT_TYPE}"/>'
        '<Override PartName="/word/styles.xml" '
        f'ContentType="{STYLES_CONTENT_TYPE}"/>'
        "</Types>"
    ).encode()


def _package_rels() -> bytes:
    return (
        f'<Relationships xmlns="{REL_NS}">'
        f'<Relationship Id="rId1" Type="{REL_TYPE_OFFICE_DOCUMENT}" '
        f'Target="{DOCUMENT_PART}"/>'
        "</Relationships>"
    ).encode()


def _document_rels() -> bytes:
    return (
        f'<Relationships xmlns="{REL_NS}">'
        f'<Relationship Id="rId2" Type="{REL_TYPE_STYLES}" '
        'Target="styles.xml"/>'
        "</Relationships>"
    ).encode()


def _paragraph(text: str = "", *, style: str | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{html.escape(style)}"/></w:pPr>' if style else ""
    runs = f"<w:r><w:t>{html.escape(text)}</w:t></w:r>" if text else ""
    return f"<w:p>{ppr}{runs}</w:p>"


def _sect_pr(*inner: str) -> str:
    return "<w:sectPr>" + "".join(inner) + "</w:sectPr>"


def _break_paragraph(sect_pr: str = "<w:sectPr/>") -> str:
    return f"<w:p><w:pPr>{sect_pr}</w:pPr></w:p>"


def _document(body: str) -> bytes:
    return (
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}">'
        f"<w:body>{body}<w:sectPr/></w:body></w:document>"
    ).encode()


def _write_package(
    tmp_path: Path,
    body: str,
    *,
    name: str = "test.docx",
) -> Path:
    path = tmp_path / name
    entries = {
        CONTENT_TYPES_PART: _content_types(),
        PACKAGE_RELS_PART: _package_rels(),
        DOCUMENT_PART: _document(body),
        "word/_rels/document.xml.rels": _document_rels(),
        "word/styles.xml": STYLES_XML,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry_name, data in entries.items():
            archive.writestr(entry_name, data)
    return path


def _fake_ctx(package: DocumentPackage) -> SimpleNamespace:
    return SimpleNamespace(
        package=package,
        document=SimpleNamespace(),
        structure=SimpleNamespace(),
        format=SimpleNamespace(
            page=SimpleNamespace(
                size="A4",
                orientation="portrait",
                margins=SimpleNamespace(
                    top=1440,
                    right=1440,
                    bottom=1440,
                    left=1440,
                ),
                header_distance=720,
                footer_distance=720,
                gutter=0,
            )
        ),
        options=SimpleNamespace(),
        dry_run=False,
    )


def _pg_num(section) -> tuple[str | None, str | None]:
    element = section.sect_pr.find(qn("w:pgNumType"))
    if element is None:
        return None, None
    return element.get(qn("w:fmt")), element.get(qn("w:start"))


def _page_fields(package: DocumentPackage, part_name: str) -> int:
    return sum(
        1 for field in iter_fields_in_part(package, part_name) if field.kind is FieldKind.PAGE
    )


def _has_page_break(paragraph) -> bool:
    for br in paragraph.iter(qn("w:br")):
        if (br.get(qn("w:type")) or "").casefold() == "page":
            return True
    ppr = paragraph.find(qn("w:pPr"))
    return ppr is not None and ppr.find(qn("w:pageBreakBefore")) is not None


def _document_with_sections(tmp_path: Path) -> Path:
    body = (
        _paragraph("Sampul", style="CoverTitle")
        + _break_paragraph()
        + _paragraph("KATA PENGANTAR", style="Heading1")
        + _break_paragraph()
        + _paragraph("BAB I", style="Heading1")
        + _paragraph("Isi bab satu")
        + _break_paragraph()
        + _paragraph("BAB II", style="Heading1")
        + _paragraph("Isi bab dua")
    )
    return _write_package(tmp_path, body, name="sections.docx")


# ---------------------------------------------------------------------------
# Golden baseline
# ---------------------------------------------------------------------------


def test_golden_lower_roman_then_decimal() -> None:
    package = DocumentPackage.load(GOLDEN)
    sections = iter_sections(package)
    assert _pg_num(sections[0]) == (None, None)

    front_matter = [section for section in sections if section.kind == "front_matter"]
    assert _pg_num(front_matter[0]) == ("lowerRoman", "1")
    for section in front_matter[1:]:
        assert _pg_num(section) == ("lowerRoman", None)

    body = [section for section in sections if section.kind == "body"]
    # Word menghapus fmt default; start=1 tetap menandai awal penomoran Arab.
    assert _pg_num(body[0]) == (None, "1")
    for section in body[1:]:
        assert _pg_num(section) == (None, None)


# ---------------------------------------------------------------------------
# Stage page_numbers
# ---------------------------------------------------------------------------


def test_page_numbers_stage_sets_roman_and_arabic(tmp_path: Path) -> None:
    path = _document_with_sections(tmp_path)
    package = DocumentPackage.load(path)
    ctx = _fake_ctx(package)

    result = PageNumbersStage().run(ctx)

    assert result.stage == StageName.PAGE_NUMBERS.value
    assert result.status == "ok"
    assert result.changed is True
    sections = iter_sections(package)
    assert [section.kind for section in sections] == [
        "cover",
        "front_matter",
        "body",
        "body",
    ]
    assert _pg_num(sections[0]) == (None, None)
    assert _pg_num(sections[1]) == ("lowerRoman", "1")
    assert _pg_num(sections[2]) == ("decimal", "1")
    assert _pg_num(sections[3]) == ("decimal", None)

    second = PageNumbersStage().run(ctx)
    assert second.changed is False


def test_page_numbers_stage_cover_has_no_part(tmp_path: Path) -> None:
    package = DocumentPackage.load(_document_with_sections(tmp_path))
    PageNumbersStage().run(_fake_ctx(package))
    cover = iter_sections(package)[0]
    refs = section_header_footer(cover)
    assert refs.header is None
    assert refs.footer is None
    assert refs.first_page_header is None
    assert refs.first_page_footer is None
    assert cover.sect_pr.find(qn("w:pgNumType")) is None


def test_page_numbers_stage_front_matter_only_footer(tmp_path: Path) -> None:
    package = DocumentPackage.load(_document_with_sections(tmp_path))
    PageNumbersStage().run(_fake_ctx(package))
    front = iter_sections(package)[1]
    refs = section_header_footer(front)
    assert refs.header is None
    assert refs.footer is not None
    part_name, part_root = header_footer_part(package, refs.footer)
    assert _page_fields(package, part_name) == 1
    assert part_root.tag == qn("w:ftr")


def test_page_numbers_stage_body_has_first_page_variants(tmp_path: Path) -> None:
    package = DocumentPackage.load(_document_with_sections(tmp_path))
    PageNumbersStage().run(_fake_ctx(package))
    body = iter_sections(package)[2]
    refs = section_header_footer(body)
    assert refs.header
    assert refs.first_page_header
    assert refs.footer
    assert refs.first_page_footer
    assert body.sect_pr.find(qn("w:titlePg")) is not None

    default_header, _ = header_footer_part(package, refs.header)
    first_header, first_header_root = header_footer_part(package, refs.first_page_header)
    default_footer, _ = header_footer_part(package, refs.footer)
    first_footer, _ = header_footer_part(package, refs.first_page_footer)
    assert _page_fields(package, default_header) == 1
    assert _page_fields(package, first_header) == 0
    assert _page_fields(package, default_footer) == 1
    assert _page_fields(package, first_footer) == 1
    assert not list(first_header_root.iter(qn("w:t")))


def test_page_numbers_stage_part_content_types_and_relationships(
    tmp_path: Path,
) -> None:
    package = DocumentPackage.load(_document_with_sections(tmp_path))
    PageNumbersStage().run(_fake_ctx(package))
    relations = package.relationships(DOCUMENT_PART)
    header_rels = [rel for rel in relations if rel.rel_type.endswith("/header")]
    footer_rels = [rel for rel in relations if rel.rel_type.endswith("/footer")]
    assert header_rels
    assert footer_rels
    for rel in header_rels + footer_rels:
        part = f"word/{rel.target}"
        assert package.has_part(part)
        content_type = package.part_info(part).content_type
        assert content_type.endswith(
            "wordprocessingml.header+xml"
            if rel.rel_type.endswith("/header")
            else "wordprocessingml.footer+xml"
        )


def test_page_numbers_stage_does_not_create_blank_page(tmp_path: Path) -> None:
    package = DocumentPackage.load(_document_with_sections(tmp_path))
    PageNumbersStage().run(_fake_ctx(package))
    root = package.xml(DOCUMENT_PART)
    body = root.find(qn("w:body"))
    assert body is not None
    paragraphs = [child for child in body if child.tag == qn("w:p")]
    assert paragraphs
    assert [paragraph for paragraph in paragraphs if _has_page_break(paragraph)] == []


def test_page_numbers_stage_requires_package() -> None:
    ctx = _fake_ctx(None)  # type: ignore[arg-type]

    with pytest.raises(StageError) as excinfo:
        PageNumbersStage().run(ctx)

    assert excinfo.value.code == "STAGE-PACKAGE"
    assert "stage page_numbers" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Header body: field STYLEREF opsional
# ---------------------------------------------------------------------------


def _ctx_with_header_style(
    package: DocumentPackage,
    value: str,
) -> SimpleNamespace:
    ctx = _fake_ctx(package)
    ctx.format.page.header_style_ref = value
    return ctx


def _body_refs(package: DocumentPackage):
    return section_header_footer(iter_sections(package)[2])


def test_page_numbers_stage_without_style_ref_keeps_page_only_header(
    tmp_path: Path,
) -> None:
    package = DocumentPackage.load(_document_with_sections(tmp_path))
    PageNumbersStage().run(_fake_ctx(package))
    refs = _body_refs(package)
    part_name, root = header_footer_part(package, refs.header)

    expected = page_part(
        "header",
        align="right",
        size_half_points=BODY_HEADER_SIZE_HALF_POINTS,
    )
    assert sha256_c14n(root) == sha256_c14n(expected)
    assert [field.instruction.strip() for field in iter_fields_in_part(package, part_name)] == [
        "PAGE"
    ]


@pytest.mark.parametrize("configured", ["Heading 1", "Heading1"])
def test_page_numbers_stage_body_header_style_ref_writes_styleref(
    tmp_path: Path,
    configured: str,
) -> None:
    package = DocumentPackage.load(_document_with_sections(tmp_path))
    ctx = _ctx_with_header_style(package, configured)

    PageNumbersStage().run(ctx)

    refs = _body_refs(package)
    part_name, root = header_footer_part(package, refs.header)
    fields = iter_fields_in_part(package, part_name)
    assert [field_instruction(field) for field in fields] == [
        'STYLEREF "heading 1" \\n',
        'STYLEREF "heading 1"',
        "PAGE",
    ]

    for styleref in fields[:2]:
        assert styleref.begin.get(qn("w:fldCharType")) == "begin"
        assert styleref.begin.get(qn("w:dirty")) == "true"
        assert styleref.separate is not None
        assert styleref.end is not None
    paragraph = fields[0].begin.getparent().getparent()
    children = list(paragraph)
    assert children.index(fields[0].begin.getparent()) < children.index(
        fields[0].separate.getparent()
    )
    assert children.index(fields[0].separate.getparent()) < children.index(
        fields[0].end.getparent()
    )

    tabs = root.find(f".//{qn('w:tabs')}")
    assert tabs is not None
    tab = tabs.find(qn("w:tab"))
    assert tab is not None
    assert tab.get(qn("w:val")) == "right"
    assert tab.get(qn("w:pos")) == str(11906 - 1440 - 1440)


def test_page_numbers_stage_body_header_style_ref_keeps_first_page_empty(
    tmp_path: Path,
) -> None:
    package = DocumentPackage.load(_document_with_sections(tmp_path))
    PageNumbersStage().run(_ctx_with_header_style(package, "Heading 1"))

    refs = _body_refs(package)
    first_part, first_root = header_footer_part(package, refs.first_page_header)
    assert iter_fields_in_part(package, first_part) == ()
    assert not list(first_root.iter(qn("w:t")))
    assert refs.footer is not None
    assert refs.first_page_footer is not None


def test_page_numbers_stage_body_header_style_ref_idempotent(tmp_path: Path) -> None:
    package = DocumentPackage.load(_document_with_sections(tmp_path))
    ctx = _ctx_with_header_style(package, "Heading 1")

    first = PageNumbersStage().run(ctx)
    second = PageNumbersStage().run(ctx)

    assert first.changed is True
    assert second.changed is False


def test_page_numbers_stage_rejects_unknown_header_style_ref(tmp_path: Path) -> None:
    package = DocumentPackage.load(_document_with_sections(tmp_path))
    ctx = _ctx_with_header_style(package, "Heading 9")

    with pytest.raises(StageError) as excinfo:
        PageNumbersStage().run(ctx)

    assert excinfo.value.code == "STAGE-HEADER-STYLE"
    assert "Heading 9" in str(excinfo.value)


def test_page_numbers_stage_back_matter_header_has_no_styleref(
    tmp_path: Path,
) -> None:
    body = (
        _paragraph("Sampul", style="CoverTitle")
        + _break_paragraph()
        + _paragraph("KATA PENGANTAR", style="Heading1")
        + _break_paragraph()
        + _paragraph("Pendahuluan", style="Heading1")
        + _paragraph("Isi bab")
        + _break_paragraph()
        + _paragraph("DAFTAR PUSTAKA", style="Heading1")
        + _paragraph("Rujukan")
    )
    package = DocumentPackage.load(_write_package(tmp_path, body, name="back-matter.docx"))
    PageNumbersStage().run(_ctx_with_header_style(package, "Heading 1"))

    back = iter_sections(package)[3]
    assert back.kind == "back_matter"
    refs = section_header_footer(back)
    part_name, root = header_footer_part(package, refs.header)
    assert [field_instruction(field) for field in iter_fields_in_part(package, part_name)] == [
        "PAGE"
    ]
    assert not any("STYLEREF" in (node.text or "") for node in root.iter(qn("w:instrText")))


def test_body_header_explicit_break_when_heading_has_none(tmp_path: Path) -> None:
    package = DocumentPackage.load(_document_with_sections(tmp_path))
    PageNumbersStage().run(_ctx_with_header_style(package, "Heading 1"))

    body = iter_sections(package)[2]
    refs = section_header_footer(body)
    _part, root = header_footer_part(package, refs.header)
    paragraph = next(paragraph for paragraph in root.iter(qn("w:p")))
    children = list(paragraph)
    fields = iter_fields_in_part(package, header_footer_part(package, refs.header)[0])
    number_end = children.index(fields[0].end.getparent())
    title_begin = children.index(fields[1].begin.getparent())
    break_positions = [
        index for index, child in enumerate(children) if child.find(qn("w:br")) is not None
    ]
    assert len(break_positions) == 1
    assert number_end < break_positions[0] < title_begin


def test_body_header_does_not_duplicate_heading_break(tmp_path: Path) -> None:
    body = (
        _paragraph("Sampul", style="CoverTitle")
        + _break_paragraph()
        + _paragraph("KATA PENGANTAR", style="Heading1")
        + _break_paragraph()
        + '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:br/>'
        "<w:r><w:t>Pendahuluan</w:t></w:r></w:p>" + _paragraph("Isi bab")
    )
    package = DocumentPackage.load(_write_package(tmp_path, body, name="heading-break.docx"))
    PageNumbersStage().run(_ctx_with_header_style(package, "Heading 1"))

    body_section = iter_sections(package)[2]
    refs = section_header_footer(body_section)
    _part, root = header_footer_part(package, refs.header)
    assert not list(root.iter(qn("w:br")))


def test_page_numbers_rejects_character_header_style(tmp_path: Path) -> None:
    package = DocumentPackage.load(_document_with_sections(tmp_path))

    with pytest.raises(StageError) as excinfo:
        PageNumbersStage().run(_ctx_with_header_style(package, "VerbatimChar"))

    assert excinfo.value.code == "STAGE-HEADER-STYLE"
    assert "paragraph" in str(excinfo.value)


def test_page_numbers_rejects_non_heading_header_style(tmp_path: Path) -> None:
    package = DocumentPackage.load(_document_with_sections(tmp_path))

    with pytest.raises(StageError) as excinfo:
        PageNumbersStage().run(_ctx_with_header_style(package, "Plain"))

    assert excinfo.value.code == "STAGE-HEADER-STYLE"
    assert "heading" in str(excinfo.value)


def test_body_section_with_unnumbered_heading_uses_page_only_header(
    tmp_path: Path,
) -> None:
    body = (
        _paragraph("Sampul", style="CoverTitle")
        + _break_paragraph()
        + _paragraph("KATA PENGANTAR", style="Heading1")
        + _break_paragraph()
        + _paragraph("Pendahuluan", style="Heading1")
        + _paragraph("Isi")
        + _paragraph("Catatan", style="Heading1")
        + _paragraph("Isi catatan")
        + _break_paragraph()
        + _paragraph("Pembahasan", style="Heading1")
        + _paragraph("Isi pembahasan")
    )
    package = DocumentPackage.load(_write_package(tmp_path, body, name="mid-unnumbered.docx"))
    apply_heading_numbering(
        package,
        NumberingSpec(body="BAB_ROMAN"),
        body_titles=("Pendahuluan", "Pembahasan"),
    )
    ctx = _ctx_with_header_style(package, "Heading 1")
    ctx.structure.body = [
        SimpleNamespace(title="Pendahuluan"),
        SimpleNamespace(title="Pembahasan"),
    ]

    PageNumbersStage().run(ctx)

    body_section = iter_sections(package, body_titles=("Pendahuluan", "Pembahasan"))[2]
    assert body_section.kind == "body"
    refs = section_header_footer(body_section)
    part_name, root = header_footer_part(package, refs.header)
    assert [field_instruction(field) for field in iter_fields_in_part(package, part_name)] == [
        "PAGE"
    ]
    assert not any("STYLEREF" in (node.text or "") for node in root.iter(qn("w:instrText")))

"""Tes unit nomor halaman Romawi/Arab dan stage ``page_numbers``."""

import html
import zipfile
from collections.abc import Mapping
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
    REL_TYPE_FOOTER,
    REL_TYPE_OFFICE_DOCUMENT,
    REL_TYPE_STYLES,
    DocumentPackage,
)
from autooffice.docx.package.sections import (
    FOOTER_CONTENT_TYPE,
    header_footer_part,
    iter_sections,
    remove_unused_header_footer_parts,
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


def _content_types(extra: str = "") -> bytes:
    return (
        f'<Types xmlns="{CT_NS}">'
        f'<Default Extension="rels" ContentType="{RELS_CONTENT_TYPE}"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/{DOCUMENT_PART}" '
        f'ContentType="{DOCUMENT_CONTENT_TYPE}"/>'
        '<Override PartName="/word/styles.xml" '
        f'ContentType="{STYLES_CONTENT_TYPE}"/>'
        f"{extra}</Types>"
    ).encode()


def _package_rels() -> bytes:
    return (
        f'<Relationships xmlns="{REL_NS}">'
        f'<Relationship Id="rId1" Type="{REL_TYPE_OFFICE_DOCUMENT}" '
        f'Target="{DOCUMENT_PART}"/>'
        "</Relationships>"
    ).encode()


def _document_rels(extra: str = "") -> bytes:
    return (
        f'<Relationships xmlns="{REL_NS}">'
        f'<Relationship Id="rId2" Type="{REL_TYPE_STYLES}" '
        'Target="styles.xml"/>'
        f"{extra}</Relationships>"
    ).encode()


def _paragraph(text: str = "", *, style: str | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{html.escape(style)}"/></w:pPr>' if style else ""
    runs = f"<w:r><w:t>{html.escape(text)}</w:t></w:r>" if text else ""
    return f"<w:p>{ppr}{runs}</w:p>"


def _sect_pr(*inner: str) -> str:
    return "<w:sectPr>" + "".join(inner) + "</w:sectPr>"


def _break_paragraph(sect_pr: str = "<w:sectPr/>") -> str:
    return f"<w:p><w:pPr>{sect_pr}</w:pPr></w:p>"


def _document(body: str, *, final_sect: str = "<w:sectPr/>") -> bytes:
    return (
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}">'
        f"<w:body>{body}{final_sect}</w:body></w:document>"
    ).encode()


def _write_package(
    tmp_path: Path,
    body: str,
    *,
    name: str = "test.docx",
    extra_parts: Mapping[str, bytes] | None = None,
    extra_content_types: str = "",
    extra_relationships: str = "",
    final_sect: str = "<w:sectPr/>",
) -> Path:
    path = tmp_path / name
    entries = {
        CONTENT_TYPES_PART: _content_types(extra_content_types),
        PACKAGE_RELS_PART: _package_rels(),
        DOCUMENT_PART: _document(body, final_sect=final_sect),
        "word/_rels/document.xml.rels": _document_rels(extra_relationships),
        "word/styles.xml": STYLES_XML,
    }
    entries.update(extra_parts or {})
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


def _shared_footer_break(sect_pr: str = "<w:sectPr>") -> str:
    return _break_paragraph(
        sect_pr + '<w:footerReference w:type="default" r:id="rId10"/></w:sectPr>'
    )


def _document_with_shared_footer(tmp_path: Path) -> Path:
    """Tiru Pandoc: satu footer1.xml dirujuk semua section, termasuk cover."""

    body = (
        _paragraph("Sampul", style="CoverTitle")
        + _shared_footer_break()
        + _paragraph("KATA PENGANTAR", style="Heading1")
        + _shared_footer_break()
        + _paragraph("ABSTRAK", style="Heading1")
        + _shared_footer_break()
        + _paragraph("BAB I", style="Heading1")
        + _paragraph("Isi bab satu")
        + _shared_footer_break()
        + _paragraph("BAB II", style="Heading1")
        + _paragraph("Isi bab dua")
    )
    return _write_package(
        tmp_path,
        body,
        name="shared-footer.docx",
        final_sect=('<w:sectPr><w:footerReference w:type="default" r:id="rId10"/></w:sectPr>'),
        extra_parts={
            "word/footer1.xml": (
                f'<w:ftr xmlns:w="{W_NS}"><w:p><w:r><w:t>placeholder</w:t></w:r></w:p></w:ftr>'
            ).encode(),
        },
        extra_content_types=(
            f'<Override PartName="/word/footer1.xml" ContentType="{FOOTER_CONTENT_TYPE}"/>'
        ),
        extra_relationships=(
            f'<Relationship Id="rId10" Type="{REL_TYPE_FOOTER}" Target="footer1.xml"/>'
        ),
    )


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


def test_page_numbers_stage_front_matter_footer_not_shared_with_body(
    tmp_path: Path,
) -> None:
    package = DocumentPackage.load(_document_with_shared_footer(tmp_path))
    PageNumbersStage().run(_fake_ctx(package))

    sections = iter_sections(package)
    assert [section.kind for section in sections] == [
        "cover",
        "front_matter",
        "front_matter",
        "body",
        "body",
    ]
    front = section_header_footer(sections[1])
    body = section_header_footer(sections[3])
    assert front.footer is not None
    assert body.footer is not None
    assert front.footer != body.footer

    front_part, front_root = header_footer_part(package, front.footer)
    body_part, body_root = header_footer_part(package, body.footer)
    assert _page_fields(package, front_part) == 1
    assert _page_fields(package, body_part) == 1
    assert not list(front_root.iter(qn("w:vanish")))
    assert list(body_root.iter(qn("w:vanish")))
    # Part bawaan Pandoc tetap menjadi footer body tersembunyi.
    assert body_part == "word/footer1.xml"
    assert front_part != body_part


def test_page_numbers_stage_shared_footer_leaves_no_orphan_parts(
    tmp_path: Path,
) -> None:
    package = DocumentPackage.load(_document_with_shared_footer(tmp_path))
    PageNumbersStage().run(_fake_ctx(package))

    before = package.part_names()
    assert remove_unused_header_footer_parts(package) == 0
    assert package.part_names() == before


def test_page_numbers_stage_shared_footer_is_idempotent(tmp_path: Path) -> None:
    package = DocumentPackage.load(_document_with_shared_footer(tmp_path))
    ctx = _fake_ctx(package)
    PageNumbersStage().run(ctx)
    refs = [section_header_footer(section) for section in iter_sections(package)]
    parts = {
        name: package.part(name)
        for name in package.part_names()
        if name.startswith(("word/footer", "word/header"))
    }

    second = PageNumbersStage().run(ctx)

    assert second.changed is False
    assert [section_header_footer(section) for section in iter_sections(package)] == refs
    assert {
        name: package.part(name)
        for name in package.part_names()
        if name.startswith(("word/footer", "word/header"))
    } == parts


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
# Header body: hanya field PAGE
# ---------------------------------------------------------------------------


def _body_refs(package: DocumentPackage):
    return section_header_footer(iter_sections(package)[2])


def test_page_numbers_stage_body_header_is_page_only(tmp_path: Path) -> None:
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
    assert [field_instruction(field) for field in iter_fields_in_part(package, part_name)] == [
        "PAGE"
    ]
    assert [node.text for node in root.iter(qn("w:instrText"))] == [" PAGE "]


def test_page_numbers_stage_back_matter_header_is_page_only(
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
    PageNumbersStage().run(_fake_ctx(package))

    back = iter_sections(package)[3]
    assert back.kind == "back_matter"
    refs = section_header_footer(back)
    part_name, root = header_footer_part(package, refs.header)
    assert [field_instruction(field) for field in iter_fields_in_part(package, part_name)] == [
        "PAGE"
    ]
    assert not any("STYLEREF" in (node.text or "") for node in root.iter(qn("w:instrText")))


def test_body_section_with_unnumbered_heading_keeps_page_only_header(
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
    ctx = _fake_ctx(package)
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

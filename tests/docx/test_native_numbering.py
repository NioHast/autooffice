"""Tes numbering native Word pada reference turunan dan helper paragraf."""

import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from lxml import etree

from autooffice.docx.config import Format, load_format
from autooffice.docx.markdown.headings import LINE_BREAK, finalize_markdown_headings
from autooffice.docx.package import DocumentPackage
from autooffice.docx.package.native_numbering import (
    MAX_ABSTRACT_NUM_ID,
    MAX_NUM_ID,
    NUMBERING_CONTENT_TYPE,
    NUMBERING_PART,
    REL_TYPE_NUMBERING,
    NumberingError,
    NumberingSpec,
    ensure_heading_numbering,
    paragraph_numbering,
    set_paragraph_unnumbered,
    verify_heading_numbering,
)
from autooffice.docx.package.styles import StyleError, set_style_numbering, style_numbering
from autooffice.docx.stages.style_reference import (
    build_reference_docx,
    verify_reference_docx,
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@pytest.fixture(scope="module")
def format_spec() -> Format:
    return load_format("undip-msi")


def _build(
    tmp_path: Path,
    format_spec: Format,
    numbering: NumberingSpec | None = None,
) -> Path:
    output = tmp_path / "reference.docx"
    build_reference_docx(
        Path(format_spec.assets.reference_docx),
        output,
        format_spec,
        numbering=numbering,
    )
    return output


def _heading_binding(path: Path) -> tuple[int, int]:
    package = DocumentPackage.load(path)
    binding = style_numbering(package, "Heading1")
    assert binding is not None
    assert binding[1] is not None
    num_id = binding[1]
    root = package.xml(NUMBERING_PART)
    for num in root.findall(W + "num"):
        if num.get(W + "numId") != str(num_id):
            continue
        abstract = num.find(W + "abstractNumId")
        assert abstract is not None
        return num_id, int(abstract.get(W + "val"))
    raise AssertionError("numId Heading1 tidak ditemukan")


def _abstract(path: Path, abstract_id: int) -> etree._Element:
    package = DocumentPackage.load(path)
    root = package.xml(NUMBERING_PART)
    for element in root.findall(W + "abstractNum"):
        if element.get(W + "abstractNumId") == str(abstract_id):
            return element
    raise AssertionError(f"abstractNum {abstract_id} tidak ditemukan")


def _level_map(path: Path, abstract_id: int) -> dict[str, etree._Element]:
    abstract = _abstract(path, abstract_id)
    return {level.get(W + "ilvl"): level for level in abstract.findall(W + "lvl")}


def test_reference_has_numbering_part_and_dynamic_style_numpr(
    tmp_path: Path,
    format_spec: Format,
) -> None:
    reference = _build(tmp_path, format_spec)
    package = DocumentPackage.load(reference)

    verify_heading_numbering(package, NumberingSpec())
    assert package.part_info(NUMBERING_PART).content_type == NUMBERING_CONTENT_TYPE
    assert any(
        relationship.rel_type == REL_TYPE_NUMBERING
        for relationship in package.relationships("word/document.xml")
    )
    num_id, abstract_id = _heading_binding(reference)
    assert 0 < num_id < 1000
    assert 0 < abstract_id < 990
    assert style_numbering(package, "Heading1") == (0, num_id)
    assert style_numbering(package, "Heading2") == (1, num_id)
    assert style_numbering(package, "Heading3") == (2, num_id)
    assert style_numbering(package, "TOCHeading") == (None, 0)

    levels = _level_map(reference, abstract_id)
    assert levels["0"].find(W + "lvlText").get(W + "val") == "BAB %1"
    assert levels["0"].find(W + "numFmt").get(W + "val") == "upperRoman"
    assert levels["1"].find(W + "lvlText").get(W + "val") == "%1.%2."
    assert levels["2"].find(W + "lvlText").get(W + "val") == "%1.%2.%3."
    for level in ("1", "2"):
        assert levels[level].find(W + "isLgl") is not None


def test_level_children_follow_ct_lvl_order(
    tmp_path: Path,
    format_spec: Format,
) -> None:
    reference = _build(tmp_path, format_spec)
    _num_id, abstract_id = _heading_binding(reference)
    levels = _level_map(reference, abstract_id)

    for level in ("0", "1", "2"):
        tags = [
            child.tag.rsplit("}", 1)[-1] for child in levels[level] if isinstance(child.tag, str)
        ]
        expected = ["start", "numFmt", "pStyle"]
        if level != "0":
            expected.append("isLgl")
        expected.extend(["suff", "lvlText", "lvlJc", "pPr"])
        assert tags == expected


def test_reference_numbering_follows_structure_numbering(
    tmp_path: Path,
    format_spec: Format,
) -> None:
    spec = NumberingSpec(body="ARABIC_DOTTED", sub_dot=False, subsub_dot=False)
    reference = _build(tmp_path, format_spec, numbering=spec)
    package = DocumentPackage.load(reference)

    verify_heading_numbering(package, spec)
    _num_id, abstract_id = _heading_binding(reference)
    levels = _level_map(reference, abstract_id)
    assert levels["0"].find(W + "lvlText").get(W + "val") == "%1."
    assert levels["0"].find(W + "numFmt").get(W + "val") == "decimal"
    assert levels["0"].find(W + "suff").get(W + "val") == "space"
    assert levels["1"].find(W + "lvlText").get(W + "val") == "%1.%2"
    assert levels["2"].find(W + "lvlText").get(W + "val") == "%1.%2.%3"


def test_custom_toc_heading_style_gets_numid_zero(
    tmp_path: Path,
    format_spec: Format,
) -> None:
    toc_heading = replace(format_spec.toc_heading, heading_style="JudulDaftar")
    custom = replace(format_spec, toc_heading=toc_heading)
    reference = _build(tmp_path, custom)
    package = DocumentPackage.load(reference)

    assert style_numbering(package, "JudulDaftar") == (None, 0)
    verify_heading_numbering(
        package,
        NumberingSpec(),
        toc_heading_style="JudulDaftar",
    )


def test_roman_chapter_path_uses_nothing_suffix_and_heading_break(
    tmp_path: Path,
    format_spec: Format,
) -> None:
    reference = _build(tmp_path, format_spec, numbering=NumberingSpec(body="BAB_ROMAN"))
    _num_id, abstract_id = _heading_binding(reference)
    level = _level_map(reference, abstract_id)["0"]
    assert level.find(W + "lvlText").get(W + "val") == "BAB %1"
    assert level.find(W + "suff").get(W + "val") == "nothing"

    finalized = finalize_markdown_headings("# Pendahuluan\n", body="BAB_ROMAN")
    assert finalized == f"# {LINE_BREAK}PENDAHULUAN\n"


def test_ensure_heading_numbering_is_idempotent(
    tmp_path: Path,
    format_spec: Format,
) -> None:
    reference = _build(tmp_path, format_spec)
    package = DocumentPackage.load(reference)
    before = _heading_binding(reference)

    assert ensure_heading_numbering(package, NumberingSpec()) is False
    verify_heading_numbering(package, NumberingSpec())
    assert _heading_binding(reference) == before


def test_verify_rejects_reference_without_numbering_part(
    tmp_path: Path,
    format_spec: Format,
) -> None:
    reference = _build(tmp_path, format_spec)
    package = DocumentPackage.load(reference)
    package.remove_part(NUMBERING_PART)
    broken = tmp_path / "without-numbering.docx"
    package.save(broken)

    with pytest.raises(NumberingError, match="numbering"):
        verify_reference_docx(broken, format_spec)


def _copy_with_foreign_numbering(tmp_path: Path, format_spec: Format) -> Path:
    source = Path(format_spec.assets.reference_docx)
    target = tmp_path / "foreign.docx"
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info)
            if info.filename == NUMBERING_PART:
                root = etree.fromstring(data)
                abstract = etree.Element(W + "abstractNum")
                abstract.set(W + "abstractNumId", "10")
                level = etree.SubElement(abstract, W + "lvl")
                level.set(W + "ilvl", "0")
                fmt = etree.SubElement(level, W + "numFmt")
                fmt.set(W + "val", "bullet")
                text = etree.SubElement(level, W + "lvlText")
                text.set(W + "val", "x")
                root.insert(0, abstract)
                num = etree.Element(W + "num")
                num.set(W + "numId", "10")
                ref = etree.SubElement(num, W + "abstractNumId")
                ref.set(W + "val", "10")
                root.append(num)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            dst.writestr(info, data)
    return target


def test_numbering_avoids_foreign_ids_and_preserves_list(
    tmp_path: Path,
    format_spec: Format,
) -> None:
    foreign = _copy_with_foreign_numbering(tmp_path, format_spec)
    output = tmp_path / "derived.docx"

    build_reference_docx(foreign, output, format_spec)

    package = DocumentPackage.load(output)
    root = package.xml(NUMBERING_PART)
    abstracts = {element.get(W + "abstractNumId") for element in root.findall(W + "abstractNum")}
    nums = {element.get(W + "numId") for element in root.findall(W + "num")}
    assert "10" in abstracts
    assert "10" in nums
    num_id, abstract_id = _heading_binding(output)
    assert num_id != 10
    assert abstract_id != 10
    verify_heading_numbering(package, NumberingSpec())


def test_numbering_fails_when_no_free_abstract_id(
    tmp_path: Path,
    format_spec: Format,
) -> None:
    source_path = Path(format_spec.assets.reference_docx)
    target = tmp_path / "full.docx"
    with (
        zipfile.ZipFile(source_path) as src,
        zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for info in src.infolist():
            data = src.read(info)
            if info.filename == NUMBERING_PART:
                root = etree.Element(W + "numbering", nsmap={"w": W[1:-1]})
                for abstract_id in range(1, MAX_ABSTRACT_NUM_ID + 1):
                    abstract = etree.SubElement(root, W + "abstractNum")
                    abstract.set(W + "abstractNumId", str(abstract_id))
                    level = etree.SubElement(abstract, W + "lvl")
                    level.set(W + "ilvl", "0")
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            dst.writestr(info, data)
    package = DocumentPackage.load(target)

    with pytest.raises(NumberingError, match="tidak ada"):
        ensure_heading_numbering(package, NumberingSpec())


def test_numbering_fails_on_foreign_heading_style_binding(
    tmp_path: Path,
    format_spec: Format,
) -> None:
    foreign = _copy_with_foreign_numbering(tmp_path, format_spec)
    package = DocumentPackage.load(foreign)
    set_style_numbering(package, "Heading1", num_id=10, level=0)

    with pytest.raises(NumberingError, match="numbering heading lain"):
        ensure_heading_numbering(package, NumberingSpec())


def test_set_paragraph_unnumbered_writes_numid_zero_once() -> None:
    paragraph = etree.fromstring(
        f'<w:p xmlns:w="{W[1:-1]}">'
        '<w:pPr><w:pStyle w:val="Heading1"/><w:spacing w:after="0"/></w:pPr>'
        "<w:r><w:t>Lampiran</w:t></w:r>"
        "</w:p>"
    )

    assert set_paragraph_unnumbered(paragraph) is True
    assert set_paragraph_unnumbered(paragraph) is False

    assert paragraph_numbering(paragraph) == (None, 0)
    ppr = paragraph.find(W + "pPr")
    assert ppr is not None
    assert [child.tag.rsplit("}", 1)[-1] for child in ppr][:2] == ["pStyle", "numPr"]


def test_set_style_numbering_rejects_character_style(
    tmp_path: Path,
    format_spec: Format,
) -> None:
    reference = _build(tmp_path, format_spec)
    package = DocumentPackage.load(reference)
    _num_id, _abstract_id = _heading_binding(reference)

    with pytest.raises(StyleError, match="paragraph"):
        set_style_numbering(package, "VerbatimChar", num_id=MAX_NUM_ID, level=0)

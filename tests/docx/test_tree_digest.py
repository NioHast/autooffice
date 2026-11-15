"""Tes ``tree_digest`` dan deteksi perubahan pada stage DOCX."""

import hashlib
import zipfile
from types import SimpleNamespace

import pytest
from lxml import etree

import autooffice.docx.package.xml as xml_module
from autooffice.docx.package import DOCUMENT_PART, DocumentPackage
from autooffice.docx.package.io import ZipEntry
from autooffice.docx.package.xml import parse_xml, sha256_c14n, tree_digest
from autooffice.docx.stages.normalize import NormalizeStage
from autooffice.docx.stages.numbering import NumberingStage
from autooffice.docx.stages.sections import SectionsStage

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W = f"{{{W_NS}}}"

NUMBERING_PART = "word/numbering.xml"


def _entry(name: str, data: bytes) -> ZipEntry:
    info = zipfile.ZipInfo(name, date_time=(2020, 1, 2, 3, 4, 6))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    info.create_system = 3
    return ZipEntry(name, data, info)


def _package(parts: dict[str, bytes]) -> DocumentPackage:
    return DocumentPackage([_entry(name, data) for name, data in parts.items()])


def _document(body: str) -> bytes:
    return (
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}"><w:body>{body}</w:body></w:document>'
    ).encode()


def _numbering() -> bytes:
    levels = "".join(
        f'<w:lvl w:ilvl="{level}"><w:start w:val="1"/>'
        '<w:numFmt w:val="decimal"/>'
        f'<w:lvlText w:val="%{level + 1}."/></w:lvl>'
        for level in range(9)
    )
    return (
        f'<w:numbering xmlns:w="{W_NS}">'
        f'<w:abstractNum w:abstractNumId="0">{levels}</w:abstractNum>'
        '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
        "</w:numbering>"
    ).encode()


# ---------------------------------------------------------------------------
# tree_digest
# ---------------------------------------------------------------------------


def test_tree_digest_matches_serialized_bytes() -> None:
    root = parse_xml(_document("<w:p><w:r><w:t>Isi</w:t></w:r></w:p>"))
    expected = hashlib.sha256(etree.tostring(root, encoding="utf-8")).hexdigest()

    assert tree_digest(root) == expected
    assert tree_digest(root.getroottree()) == expected
    assert len(expected) == 64


def test_tree_digest_changes_on_real_mutation() -> None:
    root = parse_xml(_document("<w:p><w:r><w:t>Isi</w:t></w:r></w:p>"))
    paragraph = root.find(f"{W}body/{W}p")
    assert paragraph is not None
    text = paragraph.find(f"{W}r/{W}t")
    assert text is not None

    initial = tree_digest(root)
    assert tree_digest(root) == initial

    text.text = "Isi berubah"
    assert tree_digest(root) != initial
    after_text = tree_digest(root)

    paragraph.set(f"{W}rsidR", "00ABCDEF")
    assert tree_digest(root) != after_text
    after_attribute = tree_digest(root)

    etree.SubElement(paragraph, f"{W}bookmarkStart")
    assert tree_digest(root) != after_attribute
    after_child = tree_digest(root)

    paragraph.remove(paragraph[-1])
    assert tree_digest(root) != after_child


def test_tree_digest_counts_docx_noise_stripped_by_c14n() -> None:
    root = parse_xml(_document("<w:p><w:r><w:t>Isi</w:t></w:r></w:p>"))
    canonical = sha256_c14n(root)
    digest = tree_digest(root)

    paragraph = root.find(f"{W}body/{W}p")
    assert paragraph is not None
    paragraph.set(f"{W}rsidR", "00ABCDEF")
    etree.SubElement(paragraph, f"{W}proofErr", {f"{W}type": "spellStart"})

    assert sha256_c14n(root) == canonical
    assert tree_digest(root) != digest


def test_tree_digest_skips_deepcopy_and_canonicalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = parse_xml(_document("<w:p><w:r><w:t>Isi</w:t></w:r></w:p>"))
    expected = hashlib.sha256(etree.tostring(root, encoding="utf-8")).hexdigest()

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("tree_digest tidak boleh memakai jalur canonical")

    monkeypatch.setattr(xml_module.copy, "deepcopy", fail)
    monkeypatch.setattr(xml_module, "canonicalize_xml", fail)

    assert tree_digest(root) == expected


def test_tree_digest_rejects_invalid_input() -> None:
    with pytest.raises(xml_module.XmlError, match="digest"):
        tree_digest("bukan elemen")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Stage representative
# ---------------------------------------------------------------------------


def test_normalize_stage_reports_change_then_idempotent() -> None:
    package = _package({DOCUMENT_PART: _document("<w:p><w:r><w:t>Isi</w:t></w:r></w:p>")})
    before = tree_digest(package.xml(DOCUMENT_PART))
    ctx = SimpleNamespace(package=package)

    first = NormalizeStage().run(ctx)
    assert first.changed is True
    assert tree_digest(package.xml(DOCUMENT_PART)) != before

    second = NormalizeStage().run(ctx)
    assert second.changed is False


def test_numbering_stage_reports_change_then_idempotent() -> None:
    body = (
        '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
        "<w:r><w:t>Langkah</w:t></w:r></w:p>"
    )
    package = _package(
        {
            DOCUMENT_PART: _document(body),
            NUMBERING_PART: _numbering(),
        }
    )
    before_document = tree_digest(package.xml(DOCUMENT_PART))
    before_numbering = tree_digest(package.xml(NUMBERING_PART))
    ctx = SimpleNamespace(package=package)

    first = NumberingStage().run(ctx)
    assert first.changed is True
    assert tree_digest(package.xml(DOCUMENT_PART)) != before_document
    assert tree_digest(package.xml(NUMBERING_PART)) != before_numbering

    second = NumberingStage().run(ctx)
    assert second.changed is False


def test_sections_stage_reports_change_then_idempotent() -> None:
    body = (
        '<w:p><w:r><w:t>Isi</w:t></w:r></w:p><w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
    )
    package = _package({DOCUMENT_PART: _document(body)})
    before = tree_digest(package.xml(DOCUMENT_PART))
    margins = SimpleNamespace(top=1440, right=1440, bottom=1440, left=1440)
    page = SimpleNamespace(
        size="A4",
        orientation="portrait",
        margins=margins,
        header_distance=720,
        footer_distance=720,
        gutter=0,
    )
    ctx = SimpleNamespace(package=package, structure=None, format=SimpleNamespace(page=page))

    first = SectionsStage().run(ctx)
    assert first.changed is True
    assert tree_digest(package.xml(DOCUMENT_PART)) != before

    second = SectionsStage().run(ctx)
    assert second.changed is False

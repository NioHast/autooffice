"""Gate parity style DOCX: output Pandoc tidak boleh membawa style baru.

Fixture ``tests/fixtures/docx/kitchen-sink`` memancing blok dan properti yang
ditulis Pandoc untuk dokumen produksi: heading 1-5, paragraf, daftar rapat dan
renggang, blockquote, blok kode ber-highlight dan tanpa bahasa, kode sebaris,
tabel dan caption, gambar dan caption, footnote, sitasi, garis horizontal,
serta format inline.

``reference.docx`` sengaja tidak lagi memuat ``Heading6``-``Heading9``,
``DefinitionTerm``/``Definition``, dan ``HTMLPreformatted``/``HTMLCode``.
Dokumen yang memakai heading level 6+, definition list, atau blok HTML mentah
akan memakai atau memicu impor style yang tidak ada di reference sehingga gate
ini gagal; tambahkan kembali style tersebut ke reference bila konstruksinya
memang didukung.

Tes menjalankan Pandoc lewat :func:`build_pandoc_command` milik stage
``pandoc`` supaya flag yang diuji identik dengan produksi, lalu membandingkan
dua arah terhadap ``reference.docx`` turunan:

- style yang ada di output tetapi tidak ada di reference = Pandoc mengimpor
  style sendiri (gate ini gagal);
- style yang dipakai output tetapi tidak ada di reference = konstruksi
  dokumen memakai style yang tidak didukung (gate ini gagal);
- style yang ada di keduanya harus punya definisi XML yang sama.

Bila Pandoc kelak menambah style baru, tes gagal dan menyebut ``styleId`` yang
hilang sehingga style tersebut harus dideklarasikan di
:func:`style_specs_for_format`.
"""

import os
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from lxml import etree

from autooffice.docx.config import Format, load_format
from autooffice.docx.package import DocumentPackage
from autooffice.docx.package.native_numbering import NumberingSpec, verify_heading_numbering
from autooffice.docx.package.xml import sha256_c14n
from autooffice.docx.stages.pandoc import (
    build_pandoc_command,
    build_pandoc_metadata,
    find_pandoc,
    run_pandoc,
    write_metadata_file,
)
from autooffice.docx.stages.style_reference import (
    PANDOC_HIGHLIGHT_STYLES,
    build_reference_docx,
    style_specs_for_format,
)
from tests._helpers.pandoc import pandoc_available

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "docx" / "kitchen-sink"
FORMAT_ID = "undip-msi"

# Style yang harus benar-benar dipakai fixture agar gate tidak lolos karena
# fixture kehilangan konstruksi. Daftar ini adalah style yang ditulis Pandoc
# untuk konstruksi di atas; style lain yang sah (mis. token highlighting lain)
# tidak dipaksakan.
REQUIRED_USED_STYLES = frozenset(
    {
        "Bibliography",
        "BlockText",
        "BodyText",
        "CaptionedFigure",
        "Compact",
        "FirstParagraph",
        "FootnoteReference",
        "FootnoteText",
        "Heading1",
        "Heading2",
        "Heading3",
        "Heading4",
        "Heading5",
        "Hyperlink",
        "ImageCaption",
        "KeywordTok",
        "SourceCode",
        "Table",
        "TableCaption",
        "VerbatimChar",
    }
)

# Style yang sengaja dihapus dari ``reference.docx``. Fixture tidak boleh
# memakai konstruksi yang memicunya; bila Pandoc tetap mengimpor salah satu
# style ini, gate ``test_pandoc_imports_no_style_outside_reference`` gagal.
RETIRED_STYLES = frozenset(
    {
        "DefinitionTerm",
        "Definition",
        "HTMLPreformatted",
        "HTMLCode",
        "Heading6",
        "Heading7",
        "Heading8",
        "Heading9",
        "Heading6Char",
        "Heading7Char",
        "Heading8Char",
        "Heading9Char",
    }
)

FOOTNOTE_STYLES = frozenset({"FootnoteText", "FootnoteBlockText", "FootnoteReference"})


@pytest.fixture(scope="module")
def format_spec() -> Format:
    return load_format(FORMAT_ID)


def _styles(path: Path) -> dict[str, etree._Element]:
    """Peta ``styleId`` ke elemen ``w:style`` dari ``word/styles.xml``."""

    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/styles.xml"))
    styles = [style for style in root.findall(f"{W}style") if style.get(f"{W}styleId") is not None]
    ids = [style.get(f"{W}styleId") for style in styles]
    assert len(ids) == len(set(ids)), f"styleId duplikat di {path.name}: {ids}"
    return {style.get(f"{W}styleId"): style for style in styles}


def _style_ids(path: Path) -> frozenset[str]:
    return frozenset(_styles(path))


def _used_style_ids(path: Path) -> frozenset[str]:
    """Gabungan ``pStyle``/``rStyle``/``tblStyle`` di document + footnotes."""

    used: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        for name in ("word/document.xml", "word/footnotes.xml"):
            if name not in archive.namelist():
                continue
            root = etree.fromstring(archive.read(name))
            for tag in ("pStyle", "rStyle", "tblStyle"):
                for element in root.iter(f"{W}{tag}"):
                    value = element.get(f"{W}val")
                    if value:
                        used.add(value)
    return frozenset(used)


def _differing_children(left: etree._Element, right: etree._Element) -> list[str]:
    """Nama child ``w:pPr``/``w:rPr`` yang berbeda antara dua style."""

    differing: list[str] = []
    for container in ("pPr", "rPr"):
        left_container = left.find(f"{W}{container}")
        right_container = right.find(f"{W}{container}")
        left_children = {} if left_container is None else _child_map(left_container)
        right_children = {} if right_container is None else _child_map(right_container)
        for tag in sorted(set(left_children) | set(right_children)):
            if left_children.get(tag) != right_children.get(tag):
                differing.append(f"{container}/{tag}")
    return differing


def _child_map(container: etree._Element) -> dict[str, bytes]:
    return {
        etree.QName(child).localname: etree.tostring(child, method="c14n")
        for child in container
        if isinstance(child.tag, str)
    }


@pytest.fixture(scope="module")
def parity_build(
    tmp_path_factory: pytest.TempPathFactory,
    format_spec: Format,
) -> tuple[Path, Path]:
    """Derive reference lalu jalankan Pandoc dengan flag produksi.

    Mengembalikan ``(reference_docx, output_docx)``.
    """

    if not pandoc_available():
        message = (
            "Pandoc tidak tersedia; gate parity style tidak dapat dijalankan. "
            "Pasang Pandoc atau set AUTOOFFICE_REQUIRE_PANDOC=1 untuk memaksa gagal."
        )
        if os.environ.get("CI") or os.environ.get("AUTOOFFICE_REQUIRE_PANDOC"):
            pytest.fail(message)
        pytest.skip(message)
    executable = find_pandoc()
    assert executable is not None

    root = tmp_path_factory.mktemp("style-parity")
    reference = root / "reference.docx"
    build_reference_docx(Path(format_spec.assets.reference_docx), reference, format_spec)

    bibliography = root / "references.bib"
    shutil.copyfile(FIXTURE / "references.bib", bibliography)
    document = SimpleNamespace(metadata=SimpleNamespace(lang="id-ID"))
    metadata = write_metadata_file(
        root / "metadata.json",
        build_pandoc_metadata(document, format_spec, bibliography=bibliography),
    )
    output = root / "kitchen-sink.docx"
    command = build_pandoc_command(
        executable,
        markdown=FIXTURE / "document.md",
        output=output,
        reference_docx=reference,
        bibliography=bibliography,
        csl=format_spec.citation.csl,
        metadata_file=metadata,
        resource_paths=(FIXTURE,),
        citeproc=True,
        top_level_division="chapter",
        toc=False,
    )
    run_pandoc(command)
    return reference, output


def test_reference_declares_all_pandoc_highlight_styles(
    tmp_path: Path,
    format_spec: Format,
) -> None:
    reference = tmp_path / "reference.docx"
    build_reference_docx(Path(format_spec.assets.reference_docx), reference, format_spec)

    styles = _styles(reference)
    missing = sorted(set(PANDOC_HIGHLIGHT_STYLES) - set(styles))
    assert missing == [], f"style token Pandoc belum dideklarasikan: {missing}"

    for style_id in PANDOC_HIGHLIGHT_STYLES:
        style = styles[style_id]
        assert style.get(f"{W}type") == "character", style_id
        based_on = style.find(f"{W}basedOn")
        assert based_on is not None, style_id
        assert based_on.get(f"{W}val") == "VerbatimChar", style_id

    keyword = styles["KeywordTok"]
    rpr = keyword.find(f"{W}rPr")
    assert rpr is not None
    color = rpr.find(f"{W}color")
    assert color is not None
    assert color.get(f"{W}val") == "007020"
    assert rpr.find(f"{W}b") is not None


def test_style_specs_cover_every_highlight_style(format_spec: Format) -> None:
    specs = style_specs_for_format(format_spec)

    missing = sorted(set(PANDOC_HIGHLIGHT_STYLES) - set(specs))
    assert missing == [], f"style_specs_for_format belum memuat: {missing}"


def test_reference_omits_retired_styles_and_keeps_footnotes(
    tmp_path: Path,
    format_spec: Format,
) -> None:
    reference = tmp_path / "reference.docx"
    build_reference_docx(Path(format_spec.assets.reference_docx), reference, format_spec)

    styles = _styles(reference)
    present = sorted(RETIRED_STYLES & set(styles))
    assert present == [], f"style yang sudah dipensiunkan muncul lagi di reference: {present}"

    missing_footnotes = sorted(FOOTNOTE_STYLES - set(styles))
    assert missing_footnotes == [], (
        f"style footnote wajib tetap ada di reference: {missing_footnotes}"
    )


def test_pandoc_imports_no_style_outside_reference(
    parity_build: tuple[Path, Path],
) -> None:
    reference, output = parity_build
    reference_ids = _style_ids(reference)
    output_ids = _style_ids(output)

    imported = sorted(output_ids - reference_ids)
    assert imported == [], (
        "Pandoc mengimpor style yang tidak ada di reference turunan: "
        f"{imported}. Deklarasikan di style_specs_for_format()/format.yaml."
    )

    undeclared = sorted(_used_style_ids(output) - reference_ids)
    assert undeclared == [], (
        "Pandoc memakai style yang tidak dideklarasikan reference turunan: "
        f"{undeclared}. Konstruksi fixture memakai style yang sudah dipensiunkan "
        "atau style baru belum dideklarasikan di style_specs_for_format()/format.yaml."
    )


def test_pandoc_keeps_shared_style_definitions_identical(
    parity_build: tuple[Path, Path],
) -> None:
    reference, output = parity_build
    reference_styles = _styles(reference)
    output_styles = _styles(output)

    drift: dict[str, list[str]] = {}
    for style_id in sorted(set(reference_styles) & set(output_styles)):
        left = reference_styles[style_id]
        right = output_styles[style_id]
        if sha256_c14n(left) == sha256_c14n(right):
            continue
        differing = _differing_children(left, right)
        drift[style_id] = differing or ["atribut/style"]

    assert drift == {}, f"properti style berubah antara reference dan output Pandoc: {drift}"


def test_pandoc_preserves_native_heading_numbering(
    parity_build: tuple[Path, Path],
) -> None:
    _reference, output = parity_build

    with zipfile.ZipFile(output) as archive:
        numbering = etree.fromstring(archive.read("word/numbering.xml"))
        styles = etree.fromstring(archive.read("word/styles.xml"))

    heading1 = None
    for style in styles.findall(f"{W}style"):
        if style.get(f"{W}styleId") == "Heading1":
            heading1 = style
    assert heading1 is not None
    num_pr = heading1.find(f"{W}pPr/{W}numPr")
    assert num_pr is not None
    assert num_pr.find(f"{W}ilvl").get(f"{W}val") == "0"
    num_id = int(num_pr.find(f"{W}numId").get(f"{W}val"))
    assert 0 < num_id < 1000

    num = next(
        element
        for element in numbering.findall(f"{W}num")
        if element.get(f"{W}numId") == str(num_id)
    )
    abstract_id = int(num.find(f"{W}abstractNumId").get(f"{W}val"))
    assert 0 < abstract_id < 990
    assert any(
        element.get(f"{W}abstractNumId") == str(abstract_id)
        for element in numbering.findall(f"{W}abstractNum")
    )
    verify_heading_numbering(DocumentPackage.load(output), NumberingSpec())


def test_kitchen_sink_exercises_required_styles(
    parity_build: tuple[Path, Path],
) -> None:
    _reference, output = parity_build
    used = _used_style_ids(output)

    missing = sorted(REQUIRED_USED_STYLES - used)
    assert missing == [], (
        "fixture kitchen-sink tidak lagi memancing style berikut: "
        f"{missing}. Gate parity style kehilangan cakupan."
    )

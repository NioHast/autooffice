"""Tes acceptance struktur DOCX dari tiga contoh nyata.

Setiap test membangun DOCX ke ``tmp_path`` lalu memeriksa part OOXML
``word/document.xml``, ``word/styles.xml``, dan ``word/numbering.xml`` tanpa
Microsoft Word.
"""

import os
import re
import shutil
from pathlib import Path

import pytest

from autooffice.docx.command import build_docx
from autooffice.docx.package import DocumentPackage
from autooffice.docx.package.fields import field_instruction, iter_fields
from autooffice.docx.package.names import W_P, W_SECTPR
from autooffice.docx.package.paragraphs import paragraph_style_id, paragraph_text
from autooffice.docx.package.styles import style_numbering
from autooffice.docx.package.xml import qn
from autooffice.docx.stages.plantuml import extract_blocks

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_ROOT = REPO_ROOT / "examples"
DEFAULT_PLANTUML_DIR = Path("C:/Users/nioha/AppData/Local/Programs/autooffice-plantuml")
CAPTION_RE = re.compile(r"^(Tabel|Gambar) \d+\.\d+\b")
LIST_TOC_RE = re.compile(r'\\c\s+"([^"]+)"')
SEQ_CHAPTER_SWITCH_RE = re.compile(r"\\s\s+1\b")
JAVA_STARTUP_OPTIONS = "-XX:TieredStopAtLevel=1"
EXPECTED_SECTION_COUNTS = {"thesis": 13, "proposal": 7, "assignment": 5}
EXPECTED_NUM_PR_PATTERNS = {
    "thesis": "TTTTTFFFFFTT",
    "proposal": "TFFFFT",
    "assignment": "FFFT",
}
EXPECTED_HEADING_CAPTION_COUNTS = {"thesis": 36, "proposal": 14, "assignment": 15}


def _java_available() -> bool:
    """True bila executable Java dapat ditemukan dari environment atau PATH."""

    configured = os.environ.get("AUTOOFFICE_JAVA")
    if configured:
        return Path(configured).expanduser().is_file() or shutil.which(configured) is not None
    home = os.environ.get("JAVA_HOME")
    if home:
        executable = "java.exe" if os.name == "nt" else "java"
        if (Path(home).expanduser() / "bin" / executable).is_file():
            return True
    return shutil.which("java") is not None


def _ensure_plantuml(monkeypatch: pytest.MonkeyPatch) -> None:
    """Siapkan PlantUML dari environment atau instalasi bawaan, atau skip tes."""

    # PlantUML membuka JVM baru per diagram. Mode kompilasi bertingkat penuh
    # hanya menambah waktu startup dan tidak mengubah PNG yang dihasilkan.
    if "JAVA_TOOL_OPTIONS" not in os.environ:
        monkeypatch.setenv("JAVA_TOOL_OPTIONS", JAVA_STARTUP_OPTIONS)

    configured = os.environ.get("AUTOOFFICE_PLANTUML")
    if configured:
        executable = Path(configured).expanduser()
        if not executable.is_file() and shutil.which(configured) is None:
            pytest.skip(
                f"AUTOOFFICE_PLANTUML tidak menunjuk berkas yang dapat dijalankan: {configured}"
            )
        if executable.suffix.lower() == ".jar" and not _java_available():
            pytest.skip("PlantUML .jar membutuhkan Java: set AUTOOFFICE_JAVA atau JAVA_HOME")
        return
    if shutil.which("plantuml") is not None:
        return
    default_jar = DEFAULT_PLANTUML_DIR / "plantuml.jar"
    default_java = DEFAULT_PLANTUML_DIR / "jre" / "bin" / "java.exe"
    if default_jar.is_file() and default_java.is_file():
        monkeypatch.setenv("AUTOOFFICE_PLANTUML", str(default_jar))
        monkeypatch.setenv("AUTOOFFICE_JAVA", str(default_java))
        return
    pytest.skip(
        "PlantUML tidak tersedia: set AUTOOFFICE_PLANTUML (dan AUTOOFFICE_JAVA untuk .jar) "
        f"atau pasang {DEFAULT_PLANTUML_DIR}"
    )


def _requires_plantuml(example: Path) -> bool:
    """True bila ``document.md`` contoh memuat blok PlantUML."""

    markdown = (example / "document.md").read_text(encoding="utf-8")
    return bool(extract_blocks(markdown, path=example / "document.md"))


def _build_example(
    name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> DocumentPackage:
    """Salin contoh ke ``tmp_path``, bangun DOCX, lalu muat paketnya."""

    source = EXAMPLES_ROOT / f"{name}-single"
    if _requires_plantuml(source):
        _ensure_plantuml(monkeypatch)
    project = tmp_path / name
    shutil.copytree(source, project, ignore=shutil.ignore_patterns(".laporan*", "out"))
    result = build_docx(project / "document.md", out=tmp_path / f"{name}-out")
    assert result.docx.is_file(), f"DOCX tidak terbentuk: {result.docx}"
    return DocumentPackage.load(result.docx)


def _section_count(package: DocumentPackage) -> int:
    """Jumlah ``w:sectPr`` di ``word/document.xml``, termasuk section break."""

    return len(tuple(package.xml("word/document.xml").iter(W_SECTPR)))


def _field_instructions(package: DocumentPackage) -> tuple[str, ...]:
    """Instruksi seluruh field ``word/document.xml`` tanpa spasi pinggir."""

    return tuple(field_instruction(field) for field in iter_fields(package))


def _toc_fields(package: DocumentPackage) -> tuple[str, ...]:
    """Instruksi field TOC utama, daftar tabel, dan daftar gambar."""

    return tuple(
        instruction
        for instruction in _field_instructions(package)
        if instruction.startswith("TOC ")
    )


def _has_switch(instruction: str, switch: str) -> bool:
    r"""True bila instruksi field memuat switch utuh, mis. ``\o`` atau ``\h``."""

    return re.search(rf"(?<!\S){re.escape(switch)}(?!\S)", instruction) is not None


def _list_toc_instructions(package: DocumentPackage) -> tuple[str, ...]:
    r"""Field TOC daftar khusus dengan switch ``\c``."""

    return tuple(
        instruction for instruction in _toc_fields(package) if LIST_TOC_RE.search(instruction)
    )


def _list_toc_labels(package: DocumentPackage) -> tuple[str, ...]:
    """Label caption pada field daftar, mis. ``Tabel`` dan ``Gambar``."""

    labels: list[str] = []
    for instruction in _list_toc_instructions(package):
        match = LIST_TOC_RE.search(instruction)
        assert match is not None
        labels.append(match.group(1))
    return tuple(labels)


def _heading_numpr_pattern(package: DocumentPackage) -> str:
    """Pola keberadaan ``w:numPr`` pada setiap paragraf ``Heading1``.

    ``T`` berarti paragraf punya override ``w:numPr`` sendiri; ``F`` berarti
    paragraf mewarisi numbering dari style ``Heading1``.
    """

    pattern: list[str] = []
    for paragraph in package.xml("word/document.xml").iter(W_P):
        if paragraph_style_id(paragraph) != "Heading1":
            continue
        properties = paragraph.find(qn("w:pPr"))
        num_pr = None if properties is None else properties.find(qn("w:numPr"))
        pattern.append("T" if num_pr is not None else "F")
    return "".join(pattern)


def _has_chapter_seq(package: DocumentPackage) -> bool:
    r"""True bila ada field ``SEQ`` dengan switch nomor bab ``\s 1``."""

    return any(
        instruction.startswith("SEQ ") and SEQ_CHAPTER_SWITCH_RE.search(instruction) is not None
        for instruction in _field_instructions(package)
    )


def _paragraph_texts(package: DocumentPackage) -> tuple[str, ...]:
    """Teks tampilan seluruh paragraf, termasuk hasil cache field."""

    return tuple(
        paragraph_text(paragraph) for paragraph in package.xml("word/document.xml").iter(W_P)
    )


def _chapter_captions(package: DocumentPackage) -> tuple[str, ...]:
    """Paragraf caption dengan nomor bab, mis. ``Tabel 2.1 ...``."""

    return tuple(text for text in _paragraph_texts(package) if CAPTION_RE.match(text) is not None)


def _heading_caption_count(package: DocumentPackage) -> int:
    """Jumlah paragraf berstyle Heading atau Caption di ``word/document.xml``."""

    total = 0
    for paragraph in package.xml("word/document.xml").iter(W_P):
        style = paragraph_style_id(paragraph) or ""
        if style.startswith("Heading") or "Caption" in style:
            total += 1
    return total


def _heading_level_zero(package: DocumentPackage) -> tuple[str | None, str | None]:
    """``(lvlText, numFmt)`` level 0 dari numbering efektif style ``Heading1``."""

    binding = style_numbering(package, "Heading1")
    assert binding is not None, "style Heading1 tidak memiliki w:numPr"
    level, num_id = binding
    assert level == 0, f"ilvl Heading1 bukan 0: {level}"
    assert num_id is not None, "style Heading1 tidak memiliki numId"

    numbering = package.xml("word/numbering.xml")
    num = next(
        (
            element
            for element in numbering.iter(qn("w:num"))
            if element.get(qn("w:numId")) == str(num_id)
        ),
        None,
    )
    assert num is not None, f"w:num {num_id} tidak ditemukan"
    abstract_element = num.find(qn("w:abstractNumId"))
    assert abstract_element is not None
    abstract_id = abstract_element.get(qn("w:val"))
    abstract = next(
        (
            element
            for element in numbering.iter(qn("w:abstractNum"))
            if element.get(qn("w:abstractNumId")) == abstract_id
        ),
        None,
    )
    assert abstract is not None, f"w:abstractNum {abstract_id} tidak ditemukan"
    level_zero = next(
        (element for element in abstract.findall(qn("w:lvl")) if element.get(qn("w:ilvl")) == "0"),
        None,
    )
    assert level_zero is not None
    lvl_text = level_zero.find(qn("w:lvlText"))
    num_fmt = level_zero.find(qn("w:numFmt"))
    assert lvl_text is not None
    assert num_fmt is not None
    return lvl_text.get(qn("w:val")), num_fmt.get(qn("w:val"))


def test_thesis_structure_has_front_matter_lists_and_chapter_captions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tesis memuat 13 section, TOC, dua daftar, pola numPr, dan caption bab."""

    package = _build_example("thesis", tmp_path, monkeypatch)

    assert _section_count(package) == EXPECTED_SECTION_COUNTS["thesis"]

    toc_fields = _toc_fields(package)
    assert len(toc_fields) == 3
    assert any(_has_switch(instruction, "\\o") for instruction in toc_fields)
    assert _list_toc_labels(package) == ("Tabel", "Gambar")
    for instruction in _list_toc_instructions(package):
        assert 'TOC \\c "' in instruction
        assert _has_switch(instruction, "\\h")
        assert _has_switch(instruction, "\\z")

    assert _heading_numpr_pattern(package) == EXPECTED_NUM_PR_PATTERNS["thesis"]
    assert _heading_caption_count(package) == EXPECTED_HEADING_CAPTION_COUNTS["thesis"]
    binding = style_numbering(package, "Heading1")
    assert binding is not None, "Heading1 harus memiliki w:numPr"
    assert binding[1] is not None, "Heading1 harus memiliki numId"

    texts = _paragraph_texts(package)
    assert any(text.startswith("Tabel 2.1") for text in texts)
    assert any(text.startswith("Gambar 3.1") for text in texts)
    assert _has_chapter_seq(package)


def test_proposal_structure_has_toc_without_lists_and_arabic_numbering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proposal memuat 7 section, TOC utama, tanpa daftar, dan nomor arab bertitik."""

    package = _build_example("proposal", tmp_path, monkeypatch)

    assert _section_count(package) == EXPECTED_SECTION_COUNTS["proposal"]
    assert _heading_numpr_pattern(package) == EXPECTED_NUM_PR_PATTERNS["proposal"]
    assert _heading_caption_count(package) == EXPECTED_HEADING_CAPTION_COUNTS["proposal"]

    toc_fields = _toc_fields(package)
    assert len(toc_fields) == 1
    assert _has_switch(toc_fields[0], "\\o")
    assert not _list_toc_instructions(package)

    lvl_text, num_fmt = _heading_level_zero(package)
    assert lvl_text == "%1."
    assert num_fmt == "decimal"
    numbering = package.xml("word/numbering.xml")
    assert not [
        element
        for element in numbering.iter(qn("w:lvlText"))
        if element.get(qn("w:val")) == "BAB %1"
    ]


def test_assignment_structure_is_compact_without_toc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assignment memakai 5 section, tanpa TOC, dan caption bernomor bab."""

    package = _build_example("assignment", tmp_path, monkeypatch)

    # Cover + tiga bab + bibliografi menghasilkan lima w:sectPr.
    assert _section_count(package) == EXPECTED_SECTION_COUNTS["assignment"]
    assert _heading_numpr_pattern(package) == EXPECTED_NUM_PR_PATTERNS["assignment"]
    assert _heading_caption_count(package) == EXPECTED_HEADING_CAPTION_COUNTS["assignment"]

    assert not _toc_fields(package)
    assert not _list_toc_instructions(package)

    # Mode caption non-bab sudah dihapus dari pipeline, sehingga caption
    # assignment saat ini juga memakai nomor bab.
    labels = {text.split(" ", 1)[0] for text in _chapter_captions(package)}
    assert labels == {"Tabel", "Gambar"}

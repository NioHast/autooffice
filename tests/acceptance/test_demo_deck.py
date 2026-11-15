"""Tes acceptance demo deck: build PPTX nyata dengan font Arial tanpa embedding."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from pptx import Presentation

from autooffice.deck.media.plantuml import PlantUmlError, find_plantuml, plantuml_version

pytestmark = [pytest.mark.integration, pytest.mark.slow]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DECK_DIR = REPO_ROOT / "examples" / "demo-deck"
EXPECTED_SLIDES = 24
BUILD_TIMEOUT_S = 900
_ANIMATION_TAGS = frozenset({"timing", "transition"})
_PRESENTATIONML_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_REMOVED_FONT_MARKERS = ("plus jakarta sans", "plusjakartasans")
_ALLOWED_TYPEFACES = frozenset({"Arial", "Cascadia Mono"})


def _skip_reason() -> str | None:
    """Alasan skip bila prasyarat eksternal build demo deck tidak tersedia."""
    executable = find_plantuml()
    if executable is None:
        return "demo deck acceptance membutuhkan PlantUML untuk merender blok diagram"
    try:
        plantuml_version(executable)
    except PlantUmlError:
        return "demo deck acceptance tidak dapat membaca versi PlantUML"
    return None


def _copy_demo_deck(destination: Path) -> Path:
    """Salin input demo deck ke direktori sementara tanpa cache build lama."""
    shutil.copytree(
        DEMO_DECK_DIR,
        destination,
        ignore=shutil.ignore_patterns(".autooffice*", "out"),
    )
    return destination / "deck.yaml"


def _run_build(deck_path: Path, out: Path) -> None:
    """Jalankan CLI build nyata untuk target pptx di direktori sementara."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "autooffice",
            "build",
            str(deck_path),
            "--target",
            "pptx",
            "--out",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=BUILD_TIMEOUT_S,
        env=environment,
    )
    assert completed.returncode == 0, (
        "build demo deck gagal "
        f"(exit {completed.returncode})\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )


def _xml_parts(package: ZipFile) -> tuple[str, ...]:
    return tuple(name for name in package.namelist() if name.lower().endswith(".xml"))


def _renderer_text_parts(package: ZipFile) -> tuple[str, ...]:
    prefixes = ("ppt/slides/", "ppt/charts/", "ppt/notesSlides/")
    return tuple(
        name
        for name in package.namelist()
        if name.lower().endswith(".xml") and name.startswith(prefixes)
    )


def _typefaces(package: ZipFile) -> set[str]:
    """Kumpulkan seluruh typeface eksplisit yang ditulis renderer."""
    values: set[str] = set()
    for name in _renderer_text_parts(package):
        root = ElementTree.fromstring(package.read(name))
        for element in root.iter():
            typeface = element.get("typeface")
            if typeface:
                values.add(typeface)
    return values


def _assert_pptx(pptx: Path) -> None:
    """PPTX berisi 24 slide, font Arial, tanpa font tertanam dan animasi."""
    assert len(Presentation(str(pptx)).slides) == EXPECTED_SLIDES

    with ZipFile(pptx) as package:
        names = package.namelist()

        assert not [
            name for name in names if name.startswith("ppt/fonts/") and name.endswith(".fntdata")
        ], "PPTX tidak boleh memuat part ppt/fonts/*.fntdata"

        presentation = ElementTree.fromstring(package.read("ppt/presentation.xml"))
        assert presentation.find(f".//{{{_PRESENTATIONML_NS}}}embeddedFontLst") is None, (
            "presentation.xml tidak boleh memuat p:embeddedFontLst"
        )

        typefaces = _typefaces(package)
        concrete = {value for value in typefaces if not value.startswith("+")}
        assert "Arial" in concrete, "PPTX tidak memakai font Arial: " + ", ".join(sorted(typefaces))
        assert concrete <= _ALLOWED_TYPEFACES, (
            "typeface di luar Arial/code ditemukan: " + ", ".join(sorted(concrete))
        )
        assert not any(
            marker in value.casefold() for value in typefaces for marker in _REMOVED_FONT_MARKERS
        ), "PPTX masih memuat Plus Jakarta Sans"
        offenders: list[str] = []
        for name in _xml_parts(package):
            root = ElementTree.fromstring(package.read(name))
            for element in root.iter():
                local_name = element.tag.rsplit("}", 1)[-1]
                if local_name in _ANIMATION_TAGS:
                    offenders.append(f"{name}: {local_name}")
        assert not offenders, "PPTX memuat timing/transition: " + ", ".join(offenders)


def test_demo_deck_builds_pptx_with_arial_and_transcript(tmp_path: Path) -> None:
    """Build demo deck nyata lalu verifikasi PPTX dan transkrip."""
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason)

    deck_path = _copy_demo_deck(tmp_path / "examples" / "demo-deck")
    out = tmp_path / "out"
    _run_build(deck_path, out)

    pptx = out / f"{deck_path.stem}.pptx"
    transcript = out / f"{deck_path.stem}.transcript.md"
    assert pptx.is_file(), f"PPTX tidak ditemukan: {pptx}"
    assert transcript.is_file(), f"transcript tidak ditemukan: {transcript}"
    assert not list(out.glob("*.pdf")), "target PDF tidak boleh menghasilkan artefak"

    _assert_pptx(pptx)
    assert transcript.read_bytes() == (deck_path.parent / "transcripts.md").read_bytes()

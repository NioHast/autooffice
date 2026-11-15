"""Tes aset font pengukuran Liberation Sans, lisensi, dan hash SHA256."""

import hashlib
from pathlib import Path

import pytest
from PIL import ImageFont

from autooffice.design.fonts import (
    ASSET_FILES,
    ASSET_HASHES,
    FONT_DIR,
    FONT_FAMILY,
    FONT_FILES,
    FONT_HASHES,
    FONT_LICENSE,
    LICENSE_FILE,
    LICENSE_SHA256,
    font_path,
    sha256,
)

TTF_MAGIC = (b"\x00\x01\x00\x00", b"true", b"ttcf", b"OTTO")


def test_font_directory_contains_exact_assets() -> None:
    assert FONT_DIR.is_dir()
    actual = {path.name for path in FONT_DIR.iterdir() if path.is_file()}
    assert actual == set(ASSET_FILES)
    assert actual == {*FONT_FILES, LICENSE_FILE}


def test_font_family_and_license_metadata() -> None:
    assert FONT_FAMILY == "Arial"
    assert FONT_LICENSE == "SIL Open Font License 1.1"
    assert FONT_FILES == (
        "LiberationSans-Regular.ttf",
        "LiberationSans-Bold.ttf",
    )
    assert set(FONT_HASHES) == set(FONT_FILES)


@pytest.mark.parametrize("file_name", FONT_FILES)
def test_font_file_exists_and_is_real_ttf(file_name: str) -> None:
    path = FONT_DIR / file_name

    assert path.is_file()
    assert path.stat().st_size > 10_000
    assert path.read_bytes()[:4] in TTF_MAGIC


@pytest.mark.parametrize(
    ("file_name", "style"),
    [
        ("LiberationSans-Regular.ttf", "Regular"),
        ("LiberationSans-Bold.ttf", "Bold"),
    ],
)
def test_font_names_match_regular_and_bold_faces(file_name: str, style: str) -> None:
    font = ImageFont.truetype(str(font_path(file_name)), 64)

    assert font.getname() == ("Liberation Sans", style)


@pytest.mark.parametrize("file_name", FONT_FILES)
def test_font_hash_matches_manifest(file_name: str) -> None:
    path = FONT_DIR / file_name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    assert digest == FONT_HASHES[file_name]
    assert digest == ASSET_HASHES[file_name]
    assert len(digest) == 64
    int(digest, 16)


@pytest.mark.parametrize(("file_name", "expected"), list(ASSET_HASHES.items()))
def test_sha256_helper_matches_manifest(file_name: str, expected: str) -> None:
    assert sha256(FONT_DIR / file_name) == expected
    assert sha256(font_path(file_name)) == expected


def test_license_file_contains_ofl_text() -> None:
    text = (FONT_DIR / LICENSE_FILE).read_text(encoding="utf-8")

    assert "Liberation" in text
    assert "Red Hat" in text
    assert "SIL OPEN FONT LICENSE" in text
    assert "Version 1.1" in text
    assert sha256(FONT_DIR / LICENSE_FILE) == LICENSE_SHA256


def test_unknown_font_asset_is_rejected() -> None:
    with pytest.raises(KeyError, match="tidak terdaftar"):
        font_path("FontTidakDikenal.ttf")


def test_sha256_detects_tampered_font_bytes(tmp_path: Path) -> None:
    original = font_path(FONT_FILES[0])
    tampered = tmp_path / original.name
    tampered.write_bytes(original.read_bytes() + b"\x00")

    digest = sha256(tampered)

    assert len(digest) == 64
    assert digest != FONT_HASHES[original.name]
    assert digest != ASSET_HASHES[original.name]

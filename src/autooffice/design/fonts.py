"""Metadata font pengukuran Liberation Sans yang dibundel AutoOffice.

Liberation Sans dipakai hanya untuk mengukur teks layout karena metriknya
kompatibel dengan Arial. Renderer PPTX menulis family Arial dan tidak menanam
font ke dalam paket.
"""

import hashlib
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

FONT_LICENSE = "SIL Open Font License 1.1"
FONT_FAMILY = "Arial"
FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "liberation-sans"
LICENSE_FILE = "OFL.txt"
FONT_FILES: tuple[str, ...] = (
    "LiberationSans-Regular.ttf",
    "LiberationSans-Bold.ttf",
)
FONT_HASHES: Mapping[str, str] = MappingProxyType(
    {
        "LiberationSans-Regular.ttf": (
            "76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8"
        ),
        "LiberationSans-Bold.ttf": (
            "788abee4c806d660e8aee46689dd8540cd4bb98da03dcc9d171ce3efd99a9173"
        ),
    }
)
LICENSE_SHA256 = "f45cc618951fffe1470140692086f7ca8a46ba81fe147cf8416bd63fb4849c61"
ASSET_FILES: tuple[str, ...] = (*FONT_FILES, LICENSE_FILE)
ASSET_HASHES: Mapping[str, str] = MappingProxyType({**FONT_HASHES, LICENSE_FILE: LICENSE_SHA256})


def font_path(file_name: str) -> Path:
    """Kembalikan path aset font yang terdaftar."""
    if file_name not in ASSET_HASHES:
        raise KeyError(f"aset font tidak terdaftar: {file_name}")
    return FONT_DIR / file_name


def sha256(path: Path) -> str:
    """Hitung digest SHA256 sebuah berkas aset."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()

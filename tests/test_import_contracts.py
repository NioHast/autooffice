"""Tes kontrak import antar modul ``autooffice``.

Kontrak didefinisikan di ``[tool.importlinter]`` pada ``pyproject.toml`` dan
diperiksa lewat entry point ``lint-imports`` dari dependency dev.
"""

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_pdf_module_is_removed() -> None:
    """The PDF/COM adapter package must not exist in the distribution."""
    assert importlib.util.find_spec("autooffice.pdf") is None


def test_import_contracts_have_no_pdf_module() -> None:
    """Import-linter contracts no longer reference the removed PDF adapter."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "autooffice.pdf" not in pyproject


@pytest.mark.integration
def test_import_contracts_respected() -> None:
    """Seluruh kontrak import di pyproject.toml harus KEPT."""
    executable = shutil.which("lint-imports")
    assert executable is not None, (
        "Entry point 'lint-imports' tidak ditemukan. Jalankan `uv sync --extra dev` lebih dulu."
    )

    result = subprocess.run(
        [executable, "--config", "pyproject.toml", "--no-cache"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, (
        f"lint-imports gagal dengan exit code {result.returncode}.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

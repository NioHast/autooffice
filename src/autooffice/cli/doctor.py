"""Perintah ``doctor``: cek dependency lokal tanpa jaringan.

Pemeriksaan memakai executable lokal dan hash aset font yang dibundel. Tidak
ada panggilan jaringan, tidak ada pembuatan file, dan tidak ada aplikasi Office
yang dijalankan.
"""

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from autooffice.errors import AutoOfficeError


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """Status satu dependency yang diperiksa ``doctor``."""

    name: str
    ok: bool
    required: bool
    detail: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Ringkasan pemeriksaan doctor."""

    checks: tuple[DoctorCheck, ...]
    targets: tuple[str, ...] | None
    ok: bool

    def to_dict(self) -> dict[str, object]:
        """Bentuk JSON deterministik untuk ``doctor --json``."""
        return {
            "ok": self.ok,
            "targets": list(self.targets) if self.targets is not None else None,
            "python": platform.python_version(),
            "platform": sys.platform,
            "checks": [
                {
                    "name": check.name,
                    "ok": check.ok,
                    "required": check.required,
                    "detail": check.detail,
                }
                for check in self.checks
            ],
        }


def doctor_report(targets: tuple[str, ...] | None) -> DoctorReport:
    """Kumpulkan seluruh hasil pemeriksaan doctor."""
    python_ok = sys.version_info >= (3, 15)
    python_detail = (
        f"{platform.python_version()} (butuh >=3.15)"
        if not python_ok
        else (platform.python_version())
    )
    pandoc = _find_tool("pandoc")
    pandoc_version = _tool_version(pandoc)
    mmdc = _find_tool("mmdc")
    mmdc_version = _tool_version(mmdc)
    font_assets_ok, font_assets_detail = _font_assets_status()
    google_ok, google_detail = _google_status()
    workspace_ok = os.access(Path.cwd(), os.W_OK)

    required = _required_names(targets)
    checks = (
        DoctorCheck(
            name="python",
            ok=python_ok,
            required="python" in required,
            detail=python_detail,
        ),
        DoctorCheck(
            name="pandoc",
            ok=bool(pandoc),
            required="pandoc" in required,
            detail=(
                f"{pandoc_version} - {pandoc}"
                if pandoc and pandoc_version
                else (pandoc or "tidak ditemukan; install Pandoc untuk DOCX")
            ),
        ),
        DoctorCheck(
            name="mmdc",
            ok=bool(mmdc),
            required=False,
            detail=(
                f"{mmdc_version} - {mmdc}"
                if mmdc and mmdc_version
                else (mmdc or "tidak ditemukan; diperlukan hanya untuk blok Mermaid")
            ),
        ),
        DoctorCheck(
            name="font-assets",
            ok=font_assets_ok,
            required="font-assets" in required,
            detail=font_assets_detail,
        ),
        DoctorCheck(
            name="google",
            ok=google_ok,
            required="google" in required,
            detail=google_detail,
        ),
        DoctorCheck(
            name="workspace",
            ok=workspace_ok,
            required=True,
            detail=str(Path.cwd()) if workspace_ok else f"tidak dapat ditulis: {Path.cwd()}",
        ),
    )

    required_ok = all(check.ok for check in checks if check.required)
    return DoctorReport(checks=checks, targets=targets, ok=required_ok)


def render_doctor(report: DoctorReport, *, json_output: bool) -> int:
    """Cetak laporan doctor dan kembalikan exit code 0/1."""
    if json_output:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for check in report.checks:
            marker = "[OK]" if check.ok else "[--]"
            requirement = " wajib" if check.required else ""
            print(f"{marker} {check.name:<12} {check.detail}{requirement}")
        print()
        if report.ok:
            print("Kesimpulan: dependency wajib untuk target yang diminta tersedia.")
        else:
            print("Kesimpulan: dependency wajib belum lengkap; periksa baris berstatus [--].")
    return 0 if report.ok else 1


def _required_names(targets: tuple[str, ...] | None) -> set[str]:
    """Dependency wajib untuk kombinasi target doctor."""

    required = {"python", "workspace"}
    if targets is None:
        required.update({"pandoc", "font-assets"})
        return required

    target_set = set(targets)
    if "docx" in target_set:
        required.add("pandoc")
    if "pptx" in target_set or "slides" in target_set:
        required.add("font-assets")
    if "slides" in target_set:
        required.add("google")
    return required


def _find_tool(name: str) -> str | None:
    if platform.system() != "Windows":
        return shutil.which(name)
    candidates: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("PROGRAMFILES")
    if name == "pandoc":
        if local:
            candidates.append(Path(local) / "Pandoc" / "pandoc.exe")
        if program_files:
            candidates.append(Path(program_files) / "Pandoc" / "pandoc.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which(f"{name}.exe") or shutil.which(name)


def _tool_version(command: str | None) -> str | None:
    if command is None:
        return None
    try:
        completed = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return None
    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    return output[0] if output else None


def _font_assets_status() -> tuple[bool, str]:
    try:
        from autooffice.design import fonts
    except ImportError as exc:  # pragma: no cover - paket rusak
        return False, f"modul font tidak dapat diimpor: {exc}"

    missing: list[str] = []
    mismatched: list[str] = []
    for name, expected in fonts.ASSET_HASHES.items():
        path = fonts.FONT_DIR / name
        if not path.is_file():
            missing.append(name)
            continue
        try:
            actual = fonts.sha256(path)
        except OSError:
            missing.append(name)
            continue
        if actual != expected:
            mismatched.append(name)
    if missing:
        return False, "aset font hilang: " + ", ".join(missing)
    if mismatched:
        return False, "hash font tidak cocok: " + ", ".join(mismatched)
    return True, f"{len(fonts.FONT_FILES)} TTF + lisensi di {fonts.FONT_DIR}"


def _module_available(name: str) -> bool:
    """Periksa spesifikasi modul tanpa gagal saat paket induknya tidak ada."""

    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError, ValueError:
        return False


def _google_status() -> tuple[bool, str]:
    """Periksa extra Google dan kredensial OAuth lokal tanpa jaringan."""

    if not _module_available("google"):
        return False, "google extra tidak terpasang"
    missing = [name for name in ("googleapiclient", "google.auth") if not _module_available(name)]
    if missing:
        return False, "extra google belum lengkap: " + ", ".join(missing)
    try:
        from autooffice.google import OAuthSettings, TokenStore

        OAuthSettings.from_environment()
        TokenStore.from_environment().require()
    except (AutoOfficeError, ImportError, OSError, ValueError) as exc:
        return (
            False,
            f"kredensial Google belum siap: {exc}; set GOOGLE_CLIENT_ID/"
            "GOOGLE_CLIENT_SECRET dan jalankan login OAuth",
        )
    return True, "extra google dan token OAuth lokal siap (tanpa jaringan)"


__all__ = [
    "DoctorCheck",
    "DoctorReport",
    "doctor_report",
    "render_doctor",
]

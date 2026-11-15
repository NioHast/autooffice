#!/usr/bin/env python3
"""Pemeriksa fitur PDF, COM, Mermaid, dan aset font yang tidak boleh kembali ke AutoOffice.

Checker memakai AST untuk mendeteksi import nyata pada ``src/``, ``tests/``, dan
``tools/``, memeriksa keberadaan path terlarang, menelusuri worktree untuk berkas
sumber Mermaid (``.mmd``), memeriksa isi direktori aset font terhadap allowlist,
lalu membaca ``pyproject.toml`` untuk dependency, extra, dan kontrak
import-linter. Literal string, assertion negatif, dan dokumentasi historis tidak
dipindai sehingga arsip keputusan tetap sah; penyebutan ``.mmd`` sebagai teks di
dokumen bukan berkas sehingga tidak pernah dilaporkan. Pemeriksaan bersifat
read-only, deterministik, dan tanpa jaringan.

Pemakaian:
    python tools/quality/check_removed_features.py
    python tools/quality/check_removed_features.py --list
    python tools/quality/check_removed_features.py --format json

Kode keluar 0 bila bersih, 1 bila ada pelanggaran, dan 2 bila akar repo atau
``pyproject.toml`` tidak dapat dibaca.
"""

import argparse
import ast
import json
import os
import re
import sys
import tomllib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRECTORIES: tuple[str, ...] = ("src", "tests", "tools")
FORBIDDEN_IMPORT_ROOTS: tuple[str, ...] = ("autooffice.pdf", "win32com", "pythoncom", "pywin32")
FORBIDDEN_PATHS: tuple[str, ...] = (
    "src/autooffice/pdf",
    "src/autooffice/deck/media/mermaid.py",
    "src/autooffice/docx/stages/office.py",
    "src/autooffice/docx/stages/pdf.py",
    "src/autooffice/docx/stages/mermaid.py",
    "src/autooffice/assets/fonts/plus-jakarta-sans",
    "tests/pdf",
    "tests/visual",
    "tests/deck/media/test_mermaid.py",
    "tests/deck/media/test_mermaid_security.py",
    "tests/docx/test_mermaid_docx.py",
    "docs/user/mermaid.md",
    "docs/contracts/mermaid.md",
    "tools/visual",
    "tools/install_fonts.py",
)
MERMAID_SOURCE_SUFFIX = ".mmd"
FONT_ASSETS_DIRECTORY = "src/autooffice/assets/fonts"
ALLOWED_FONT_DIRECTORIES: frozenset[str] = frozenset({"liberation-sans"})
FORBIDDEN_DEPENDENCIES: tuple[str, ...] = ("pywin32", "pypdf")
FORBIDDEN_EXTRAS: tuple[str, ...] = ("windows",)
FORBIDDEN_CONTRACT_MODULE = "autooffice.pdf"

CONTRACT_MENTION = re.compile(r"(?<![A-Za-z0-9_])autooffice\.pdf(?![A-Za-z0-9_])")
DEPENDENCY_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

SKIPPED_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".cache",
        ".eggs",
        ".git",
        ".hypothesis",
        ".import_linter_cache",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".venv315",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
    }
)


class RemovedFeatureError(Exception):
    """Akar repo atau konfigurasi tidak dapat dibaca."""


@dataclass(frozen=True, slots=True)
class Violation:
    """Satu temuan checker dengan lokasi berkas dan baris."""

    file: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.rule}: {self.message}"


@dataclass(frozen=True, slots=True)
class Result:
    """Ringkasan hasil pemindaian."""

    file_count: int = 0
    violations: tuple[Violation, ...] = ()


def _is_skipped_directory(name: str) -> bool:
    """True untuk cache, artefak build, dan metadata package yang diabaikan."""
    folded = name.casefold()
    return folded in SKIPPED_DIRECTORIES or folded.endswith(".egg-info")


def _python_files(root: Path) -> list[Path]:
    """Kumpulkan berkas Python dari direktori kode secara deterministik."""
    selected: dict[Path, None] = {}
    for directory in SCAN_DIRECTORIES:
        base = root / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if not path.is_file():
                continue
            relative_parts = path.relative_to(base).parts[:-1]
            if any(_is_skipped_directory(part) for part in relative_parts):
                continue
            selected[path] = None
    return sorted(selected, key=lambda item: item.relative_to(root).as_posix())


def _forbidden_root(module: str) -> str | None:
    """Kembalikan akar import terlarang yang cocok, atau None."""
    folded = module.casefold()
    for root in FORBIDDEN_IMPORT_ROOTS:
        if folded == root or folded.startswith(f"{root}."):
            return root
    return None


def _package_parts(display: str) -> tuple[str, ...]:
    """Turunkan bagian package dari path relatif berkas Python."""
    parts = list(Path(display).with_suffix("").parts)
    parts.pop()
    if parts and parts[0] == "src":
        parts.pop(0)
    return tuple(parts)


def _relative_module(node: ast.ImportFrom, package: tuple[str, ...]) -> str | None:
    """Resolve modul import relatif terhadap package berkas."""
    if node.level == 0:
        return node.module or ""
    remaining = len(package) - (node.level - 1)
    if remaining < 0:
        return None
    parts = list(package[:remaining])
    if node.module:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def _import_violations(
    node: ast.Import | ast.ImportFrom,
    display: str,
    package: tuple[str, ...],
) -> list[Violation]:
    """Periksa satu statement import dan kembalikan temuan."""
    if isinstance(node, ast.Import):
        findings: list[Violation] = []
        for alias in node.names:
            root = _forbidden_root(alias.name)
            if root is not None:
                findings.append(
                    Violation(
                        display,
                        node.lineno,
                        "forbidden-import",
                        f"import {root} dilarang; fitur PDF/COM sudah dihapus",
                    )
                )
        return findings
    base = _relative_module(node, package)
    if base is None:
        return []
    candidates = [base]
    candidates.extend(
        f"{base}.{alias.name}" if base else alias.name for alias in node.names if alias.name != "*"
    )
    for candidate in candidates:
        if _forbidden_root(candidate) is not None:
            return [
                Violation(
                    display,
                    node.lineno,
                    "forbidden-import",
                    f"import {candidate} dilarang; fitur PDF/COM sudah dihapus",
                )
            ]
    return []


def _scan_file(path: Path, display: str) -> list[Violation]:
    """Baca satu berkas dan periksa import nyata lewat AST."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=display)
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        return [
            Violation(
                display,
                0,
                "unreadable",
                f"tidak dapat diperiksa: {exc.__class__.__name__}",
            )
        ]
    package = _package_parts(display)
    findings: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            findings.extend(_import_violations(node, display, package))
    return findings


def _path_violations(root: Path) -> list[Violation]:
    """Laporkan setiap path terlarang yang masih ada."""
    findings: list[Violation] = []
    for relative in FORBIDDEN_PATHS:
        if os.path.lexists(root / relative):
            findings.append(
                Violation(
                    relative,
                    0,
                    "forbidden-path",
                    f"path {relative} dilarang; fitur PDF/COM/Mermaid sudah dihapus",
                )
            )
    return findings


def _mermaid_source_violations(root: Path) -> list[Violation]:
    """Laporkan setiap berkas sumber Mermaid (``.mmd``) di worktree.

    Penelusuran hanya memakai nama berkas, sehingga penyebutan ``.mmd`` di dalam
    dokumen historis tidak pernah dianggap temuan. Direktori cache, artefak
    build, ``.git``, ``.venv``, dan ``dist`` dilewati.
    """
    suffix = MERMAID_SOURCE_SUFFIX.casefold()
    findings: list[Violation] = []
    for current, directories, names in os.walk(root):
        directories[:] = sorted(name for name in directories if not _is_skipped_directory(name))
        base = Path(current)
        for name in sorted(names):
            if not name.casefold().endswith(suffix):
                continue
            relative = (base / name).relative_to(root).as_posix()
            findings.append(
                Violation(
                    relative,
                    0,
                    "mermaid-source",
                    f"berkas sumber Mermaid {relative} dilarang; dukungan mmdc sudah dihapus",
                )
            )
    return findings


def _font_directory_violations(root: Path) -> list[Violation]:
    """Laporkan direktori font di luar allowlist pada direktori aset font.

    Path yang sudah tercantum di ``FORBIDDEN_PATHS`` dilewati agar satu direktori
    terlarang tidak dilaporkan dua kali oleh aturan yang berbeda.
    """
    base = root / FONT_ASSETS_DIRECTORY
    if not base.is_dir():
        return []
    allowed = ", ".join(sorted(ALLOWED_FONT_DIRECTORIES))
    findings: list[Violation] = []
    for child in sorted(base.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        relative = f"{FONT_ASSETS_DIRECTORY}/{child.name}"
        if child.name.casefold() in ALLOWED_FONT_DIRECTORIES or relative in FORBIDDEN_PATHS:
            continue
        findings.append(
            Violation(
                relative,
                0,
                "forbidden-font",
                f"direktori font {relative} dilarang; aset font hanya boleh {allowed}",
            )
        )
    return findings


def _as_mapping(value: object) -> dict[object, object]:
    """Kembalikan dict bila nilai TOML berbentuk tabel, selain itu dict kosong."""
    return value if isinstance(value, dict) else {}


def _normalize_name(value: str) -> str:
    """Normalisasi nama dependency mengikuti gaya PEP 503."""
    match = DEPENDENCY_NAME.match(value.strip())
    if match is None:
        return ""
    return re.sub(r"[-_.]+", "-", match.group(0)).casefold()


def _dependency_sections(config: dict[object, object]) -> list[tuple[str, list[object]]]:
    """Kumpulkan semua daftar dependency yang dideklarasikan."""
    project = _as_mapping(config.get("project"))
    sections: list[tuple[str, list[object]]] = []
    dependencies = project.get("dependencies")
    if isinstance(dependencies, list):
        sections.append(("project.dependencies", dependencies))
    optional = _as_mapping(project.get("optional-dependencies"))
    for extra, entries in optional.items():
        if isinstance(entries, list):
            sections.append((f"project.optional-dependencies.{extra}", entries))
    groups = _as_mapping(config.get("dependency-groups"))
    for group, entries in groups.items():
        if isinstance(entries, list):
            sections.append((f"dependency-groups.{group}", entries))
    return sections


def _iter_strings(value: object) -> Iterator[str]:
    """Hasilkan semua string pada struktur TOML secara rekursif."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _config_violations(config: dict[object, object]) -> list[Violation]:
    """Periksa dependency, extra, dan kontrak import-linter."""
    findings: list[Violation] = []
    optional = _as_mapping(_as_mapping(config.get("project")).get("optional-dependencies"))
    for extra in optional:
        if _normalize_name(str(extra)) in FORBIDDEN_EXTRAS:
            findings.append(
                Violation(
                    "pyproject.toml",
                    0,
                    "forbidden-extra",
                    f"extra {extra} dilarang; fitur PDF/COM sudah dihapus",
                )
            )
    for section, entries in _dependency_sections(config):
        for entry in entries:
            if not isinstance(entry, str):
                continue
            name = _normalize_name(entry)
            if name in FORBIDDEN_DEPENDENCIES:
                findings.append(
                    Violation(
                        "pyproject.toml",
                        0,
                        "forbidden-dependency",
                        f"dependency {name} dilarang di {section}",
                    )
                )
    importlinter = _as_mapping(_as_mapping(config.get("tool")).get("importlinter"))
    for text in _iter_strings(importlinter):
        if CONTRACT_MENTION.search(text):
            findings.append(
                Violation(
                    "pyproject.toml",
                    0,
                    "forbidden-contract",
                    f"kontrak import-linter menyebut {text}",
                )
            )
    return findings


def _read_pyproject(root: Path) -> dict[object, object]:
    """Baca pyproject.toml; berkas yang tidak ada dianggap tanpa konfigurasi."""
    path = root / "pyproject.toml"
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise RemovedFeatureError(f"gagal membaca {path}: {exc}") from exc


def check(root: Path = REPO_ROOT) -> Result:
    """Pindai kode, test, tools, berkas ``.mmd``, aset font, dan konfigurasi."""
    root = root.resolve()
    files = _python_files(root)
    violations = _path_violations(root)
    violations.extend(_mermaid_source_violations(root))
    violations.extend(_font_directory_violations(root))
    for path in files:
        display = path.relative_to(root).as_posix()
        violations.extend(_scan_file(path, display))
    violations.extend(_config_violations(_read_pyproject(root)))
    unique: dict[tuple[str, int, str, str], Violation] = {}
    for item in violations:
        unique.setdefault((item.file, item.line, item.rule, item.message), item)
    ordered = tuple(
        sorted(unique.values(), key=lambda item: (item.file, item.line, item.rule, item.message))
    )
    return Result(file_count=len(files), violations=ordered)


def format_targets() -> str:
    """Render daftar target terlarang untuk ``--list``."""
    lines = [f"{'import':10} {module}" for module in FORBIDDEN_IMPORT_ROOTS]
    lines.extend(f"{'path':10} {path}" for path in FORBIDDEN_PATHS)
    lines.append(f"{'mermaid-source':10} berkas berakhiran {MERMAID_SOURCE_SUFFIX}")
    allowed_fonts = ", ".join(sorted(ALLOWED_FONT_DIRECTORIES))
    lines.append(f"{'font-dir':10} {FONT_ASSETS_DIRECTORY}: hanya {allowed_fonts}")
    lines.extend(f"{'dependency':10} {name}" for name in FORBIDDEN_DEPENDENCIES)
    lines.extend(f"{'extra':10} {name}" for name in FORBIDDEN_EXTRAS)
    lines.append(f"{'contract':10} {FORBIDDEN_CONTRACT_MODULE}")
    return "\n".join(lines)


def _report_payload(result: Result) -> dict[str, object]:
    """Representasi JSON hasil pemindaian."""
    return {
        "files": result.file_count,
        "total": len(result.violations),
        "passed": not result.violations,
        "violations": [
            {
                "file": item.file,
                "line": item.line,
                "rule": item.rule,
                "message": item.message,
            }
            for item in result.violations
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser CLI tanpa menjalankan pemeriksaan."""
    parser = argparse.ArgumentParser(
        prog="check_removed_features.py",
        description=(
            "Periksa import, path, berkas .mmd, aset font, dan konfigurasi fitur PDF/COM/Mermaid "
            "yang dihapus."
        ),
    )
    parser.add_argument("root", nargs="?", type=Path, default=REPO_ROOT, help="akar repo")
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_targets",
        help="cetak target terlarang dan keluar tanpa memindai",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="format keluaran; default text",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Jalankan checker dan kembalikan kode keluar 0, 1, atau 2."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_targets:
        print(format_targets())
        return 0
    root = args.root.resolve()
    if not root.is_dir():
        print(f"akar repo tidak ditemukan: {root}", file=sys.stderr)
        return 2
    try:
        result = check(root)
    except RemovedFeatureError as exc:
        print(f"check_removed_features: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(_report_payload(result), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Berkas diperiksa: {result.file_count}")
        print(f"Pelanggaran aktif: {len(result.violations)}")
        for item in result.violations:
            print(f"- {item}")
    return 1 if result.violations else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    raise SystemExit(main(sys.argv[1:]))

"""Tes pemeriksa fitur PDF, COM, Mermaid, dan aset font yang sudah dihapus AutoOffice."""

import json
from pathlib import Path

import pytest

from tools.quality import check_removed_features, gate

CLEAN_PYPROJECT = """\
[project]
name = "sample"
dependencies = ["lxml==6.1.3"]

[project.optional-dependencies]
dev = ["pytest==9.2.0"]
google = ["google-auth-oauthlib==1.5.0"]
"""

MERMAID_FORBIDDEN_PATHS: tuple[str, ...] = (
    "src/autooffice/deck/media/mermaid.py",
    "src/autooffice/docx/stages/mermaid.py",
    "tests/deck/media/test_mermaid.py",
    "tests/deck/media/test_mermaid_security.py",
    "tests/docx/test_mermaid_docx.py",
    "docs/user/mermaid.md",
    "docs/contracts/mermaid.md",
)


def _write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _violations(root: Path) -> tuple[check_removed_features.Violation, ...]:
    return check_removed_features.check(root).violations


def _make_forbidden_path(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if Path(relative).suffix:
        path.write_text("", encoding="utf-8")
    else:
        path.mkdir()


def test_clean_tree_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path, "pyproject.toml", CLEAN_PYPROJECT)
    _write(tmp_path, "src/autooffice/__init__.py", "")
    _write(
        tmp_path,
        "tests/test_guard.py",
        "import importlib.util\n\n"
        'assert importlib.util.find_spec("autooffice.pdf") is None\n'
        'assert "import win32com.client" not in "teks negatif"\n'
        'assert "windows" not in "extra terlarang"\n',
    )

    result = check_removed_features.check(tmp_path)
    code = check_removed_features.main([str(tmp_path)])

    assert result.file_count == 2
    assert result.violations == ()
    assert code == 0
    assert "Pelanggaran aktif: 0" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("source", "module"),
    [
        ("import win32com.client\n", "win32com"),
        ("from win32com.client import Dispatch\n", "win32com"),
        ("import pythoncom\n", "pythoncom"),
        ("from pythoncom import CoInitialize\n", "pythoncom"),
        ("import pywin32\n", "pywin32"),
    ],
)
def test_com_import_fails(tmp_path: Path, source: str, module: str) -> None:
    _write(tmp_path, "src/autooffice/com_bridge.py", source)

    findings = _violations(tmp_path)

    assert [item.rule for item in findings] == ["forbidden-import"]
    assert module in findings[0].message
    assert check_removed_features.main([str(tmp_path)]) == 1


@pytest.mark.parametrize(
    "source",
    [
        "import autooffice.pdf\n",
        "import autooffice.pdf.word\n",
        "from autooffice.pdf import word\n",
        "from autooffice import pdf\n",
    ],
)
def test_pdf_import_fails(tmp_path: Path, source: str) -> None:
    _write(tmp_path, "src/autooffice/render.py", source)

    findings = _violations(tmp_path)

    assert [item.rule for item in findings] == ["forbidden-import"]
    assert "autooffice.pdf" in findings[0].message
    assert check_removed_features.main([str(tmp_path)]) == 1


def test_relative_pdf_import_fails(tmp_path: Path) -> None:
    _write(tmp_path, "src/autooffice/__init__.py", "from . import pdf\n")

    findings = _violations(tmp_path)

    assert [item.rule for item in findings] == ["forbidden-import"]
    assert "autooffice.pdf" in findings[0].message


@pytest.mark.parametrize("relative", check_removed_features.FORBIDDEN_PATHS)
def test_forbidden_path_is_detected(tmp_path: Path, relative: str) -> None:
    _make_forbidden_path(tmp_path, relative)

    findings = _violations(tmp_path)

    assert [item.file for item in findings if item.rule == "forbidden-path"] == [relative]


def test_forbidden_path_fails_the_cli(tmp_path: Path) -> None:
    _make_forbidden_path(tmp_path, "tools/install_fonts.py")

    assert check_removed_features.main([str(tmp_path)]) == 1


def test_plus_jakarta_sans_is_a_forbidden_path() -> None:
    assert "src/autooffice/assets/fonts/plus-jakarta-sans" in check_removed_features.FORBIDDEN_PATHS


def test_plus_jakarta_sans_font_directory_fails(tmp_path: Path) -> None:
    _make_forbidden_path(tmp_path, "src/autooffice/assets/fonts/plus-jakarta-sans")

    findings = _violations(tmp_path)

    assert [item.rule for item in findings] == ["forbidden-path"]
    assert findings[0].file == "src/autooffice/assets/fonts/plus-jakarta-sans"
    assert check_removed_features.main([str(tmp_path)]) == 1


@pytest.mark.parametrize("relative", MERMAID_FORBIDDEN_PATHS)
def test_mermaid_path_is_a_forbidden_path(relative: str) -> None:
    assert relative in check_removed_features.FORBIDDEN_PATHS


@pytest.mark.parametrize("relative", MERMAID_FORBIDDEN_PATHS)
def test_mermaid_path_is_detected(tmp_path: Path, relative: str) -> None:
    _make_forbidden_path(tmp_path, relative)

    findings = _violations(tmp_path)

    assert [item.file for item in findings if item.rule == "forbidden-path"] == [relative]
    assert check_removed_features.main([str(tmp_path)]) == 1


@pytest.mark.parametrize("name", ["diagram.mmd", "diagram.MMD"])
def test_mermaid_source_file_fails(tmp_path: Path, name: str) -> None:
    _write(tmp_path, f"diagrams/{name}", "flowchart LR\n  A --> B\n")

    findings = _violations(tmp_path)

    assert [item.rule for item in findings] == ["mermaid-source"]
    assert findings[0].file == f"diagrams/{name}"
    assert "mmdc" in findings[0].message
    assert check_removed_features.main([str(tmp_path)]) == 1


@pytest.mark.parametrize("directory", [".git", ".venv", "dist"])
def test_mermaid_source_in_skipped_directory_passes(tmp_path: Path, directory: str) -> None:
    _write(tmp_path, f"{directory}/history/diagram.mmd", "flowchart LR\n")

    assert _violations(tmp_path) == ()


def test_mermaid_suffix_mentioned_as_text_passes(tmp_path: Path) -> None:
    _write(tmp_path, "docs/dev/notes.md", "Simpan sumber diagram sebagai `diagram.mmd`.\n")
    _write(tmp_path, "archive/history/lessons.md", "Berkas `.mmd` sudah dihapus.\n")
    _write(tmp_path, "src/autooffice/notes.py", 'SOURCE_SUFFIX = ".mmd"\n')

    assert _violations(tmp_path) == ()


def test_mermaid_source_is_reported_in_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(tmp_path, "diagram.mmd", "flowchart LR\n")

    code = check_removed_features.main(["--format", "json", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["total"] == 1
    assert payload["violations"][0]["rule"] == "mermaid-source"


def test_unexpected_font_directory_fails(tmp_path: Path) -> None:
    _write(tmp_path, "src/autooffice/assets/fonts/open-sans/OpenSans-Regular.ttf", "")

    findings = _violations(tmp_path)

    assert [item.rule for item in findings] == ["forbidden-font"]
    assert findings[0].file == "src/autooffice/assets/fonts/open-sans"
    assert "liberation-sans" in findings[0].message
    assert check_removed_features.main([str(tmp_path)]) == 1


def test_allowed_font_directory_passes(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/autooffice/assets/fonts/liberation-sans/LiberationSans-Regular.ttf",
        "",
    )

    assert _violations(tmp_path) == ()
    assert check_removed_features.main([str(tmp_path)]) == 0


def test_repository_font_directories_match_allowlist() -> None:
    fonts = check_removed_features.REPO_ROOT / check_removed_features.FONT_ASSETS_DIRECTORY

    names = {child.name for child in fonts.iterdir() if child.is_dir()}

    assert names == set(check_removed_features.ALLOWED_FONT_DIRECTORIES)


def test_windows_extra_is_detected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        "[project]\n"
        'name = "sample"\n'
        "\n"
        "[project.optional-dependencies]\n"
        'windows = ["pywin32==306"]\n',
    )

    rules = {item.rule for item in _violations(tmp_path)}

    assert {"forbidden-extra", "forbidden-dependency"} <= rules
    assert check_removed_features.main([str(tmp_path)]) == 1


def test_pypdf_dependency_is_detected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "sample"\ndependencies = ["pypdf>=6"]\n',
    )

    findings = _violations(tmp_path)

    assert [item.rule for item in findings] == ["forbidden-dependency"]
    assert "pypdf" in findings[0].message


def test_import_linter_contract_is_detected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        '[tool.importlinter]\nroot_packages = ["autooffice"]\n'
        "\n"
        "[[tool.importlinter.contracts]]\n"
        'name = "docx tanpa pdf"\n'
        'type = "forbidden"\n'
        'source_modules = ["autooffice.docx"]\n'
        'forbidden_modules = ["autooffice.pdf"]\n',
    )

    findings = _violations(tmp_path)

    assert [item.rule for item in findings] == ["forbidden-contract"]
    assert "autooffice.pdf" in findings[0].message


def test_json_format_reports_violations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(tmp_path, "src/autooffice/com_bridge.py", "import win32com.client\n")

    code = check_removed_features.main(["--format", "json", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["passed"] is False
    assert payload["total"] == 1
    assert payload["violations"][0]["rule"] == "forbidden-import"


def test_list_prints_targets(capsys: pytest.CaptureFixture[str]) -> None:
    code = check_removed_features.main(["--list"])

    output = capsys.readouterr().out
    assert code == 0
    for target in (
        "autooffice.pdf",
        "win32com",
        "pythoncom",
        "pywin32",
        "src/autooffice/pdf",
        "src/autooffice/deck/media/mermaid.py",
        "src/autooffice/docx/stages/mermaid.py",
        "src/autooffice/assets/fonts/plus-jakarta-sans",
        "tests/visual",
        "tests/deck/media/test_mermaid.py",
        "tests/deck/media/test_mermaid_security.py",
        "tests/docx/test_mermaid_docx.py",
        "docs/user/mermaid.md",
        "docs/contracts/mermaid.md",
        "tools/install_fonts.py",
        "mermaid-source",
        ".mmd",
        "pypdf",
        "windows",
        "liberation-sans",
    ):
        assert target in output


def test_missing_root_returns_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = check_removed_features.main([str(tmp_path / "tidak-ada")])

    assert code == 2
    assert "akar repo tidak ditemukan" in capsys.readouterr().err


def test_invalid_pyproject_returns_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(tmp_path, "pyproject.toml", '[project\nname = "sample"\n')

    code = check_removed_features.main([str(tmp_path)])

    assert code == 2
    assert "check_removed_features" in capsys.readouterr().err


def test_repository_is_clean() -> None:
    result = check_removed_features.check()

    assert result.file_count > 0
    assert result.violations == ()


def test_gate_wires_removed_features_after_no_legacy() -> None:
    steps = gate.build_steps()
    names = [step.name for step in steps]
    step = steps[names.index("removed-features")]

    assert names.index("removed-features") == names.index("no-legacy") + 1
    assert step.blocking is True
    assert step.command == ("uv", "run", "python", "tools/quality/check_removed_features.py")

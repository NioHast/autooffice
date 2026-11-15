"""Tes eksportir arsip riwayat AutoOffice."""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from tools.history import export_archive

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "history" / "export_archive.py"
LOG_NAME = "AUTO_OFFICE_EXECUTION_LOG.md"
GIT_OPTIONS = (
    "-c",
    "user.name=Uji Arsip",
    "-c",
    "user.email=arsip@example.com",
    "-c",
    "commit.gpgsign=false",
)
LOG_TEXT = """# AutoOffice Execution Log

## 2026-11-14 - Entri pertama

- File yang berubah: `src/first.py`, `docs/guide.md`, `tests/glob/**`.

## 2026-11-15 - Entri kedua

- File yang berubah: `src/second.py`, `src/first.py`.
"""


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *GIT_OPTIONS, *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed


def _git_bytes(repo: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", *GIT_OPTIONS, *arguments],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    return completed.stdout


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", message)


def _build_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _write_file(repo / "src" / "first.py", "VALUE = 1\n")
    _write_file(repo / "docs" / "guide.md", "# Panduan\n")
    _commit(repo, "tambah berkas pertama")
    _write_file(repo / "src" / "second.py", "VALUE = 2\n")
    _write_file(repo / LOG_NAME, LOG_TEXT)
    _write_file(repo / "docs" / "dev" / "agent-rules.md", "# Aturan agen\n")
    _write_file(repo / "archive" / "autooffice-history" / "lessons.jsonl", '{"lesson": "satu"}\n')
    _write_file(repo / "archive" / "autooffice-history" / "eval-cases.md", "# Kasus evaluasi\n")
    _commit(repo, "tambah log dan berkas kedua")
    _git(repo, "tag", "v1.0.0")
    return repo


@pytest.fixture(scope="module")
def archive_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build_repo(tmp_path_factory.mktemp("arsip"))


def _run_exporter(repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_export_archive_writes_verified_outputs(archive_repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "history"

    completed = _run_exporter(archive_repo, "--tag", "v1.0.0", "--out", str(out))

    assert completed.returncode == 0, completed.stderr
    assert "unggah: dilewati" in completed.stdout
    bundle = out / "autooffice-v1.0.0.bundle"
    assert bundle.is_file()
    verify = _git(archive_repo, "bundle", "verify", str(bundle))
    report = verify.stdout + verify.stderr
    assert "refs/tags/v1.0.0" in report
    tagged_log = _git_bytes(archive_repo, "show", f"v1.0.0:{LOG_NAME}")
    assert (out / LOG_NAME).read_bytes() == tagged_log
    history_map = (out / "history-map.md").read_text(encoding="utf-8")
    assert "Entri pertama" in history_map
    assert "Entri kedua" in history_map
    assert "src/first.py" in history_map
    assert "src/second.py" in history_map
    assert "Pemetaan ini berbasis file" in history_map
    assert (out / "agent-rules.md").read_bytes() == (
        archive_repo / "docs" / "dev" / "agent-rules.md"
    ).read_bytes()
    assert (out / "lessons.jsonl").read_bytes() == (
        archive_repo / "archive" / "autooffice-history" / "lessons.jsonl"
    ).read_bytes()
    assert (out / "eval-cases.md").read_bytes() == (
        archive_repo / "archive" / "autooffice-history" / "eval-cases.md"
    ).read_bytes()
    names = _verify_checksums(out)
    assert names == sorted(names)
    assert "SHA256SUMS" not in names
    assert set(names) == {
        LOG_NAME,
        "agent-rules.md",
        "autooffice-v1.0.0.bundle",
        "eval-cases.md",
        "history-map.md",
        "lessons.jsonl",
    }


def _verify_checksums(out: Path) -> list[str]:
    lines = (out / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert lines
    names: list[str] = []
    for line in lines:
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
        names.append(name)
    return names


def test_missing_tag_exits_two(archive_repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "history"

    completed = _run_exporter(archive_repo, "--tag", "v9.9.9", "--out", str(out))

    assert completed.returncode == 2
    assert "tag tidak ditemukan" in completed.stderr
    assert not out.exists()


def test_help_exits_zero() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0
    assert "--tag" in completed.stdout
    assert "--upload" in completed.stdout


def test_list_shows_available_tags(archive_repo: Path) -> None:
    completed = _run_exporter(archive_repo, "--list")

    assert completed.returncode == 0
    assert "v1.0.0" in completed.stdout


def test_export_without_upload_does_not_call_gh(
    archive_repo: Path, tmp_path: Path, monkeypatch
) -> None:
    commands: list[list[str]] = []
    original = export_archive.run_command

    def record(command: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
        commands.append(list(command))
        return original(command, cwd)

    monkeypatch.setattr(export_archive, "run_command", record)
    monkeypatch.chdir(archive_repo)

    code = export_archive.main(["--tag", "v1.0.0", "--out", str(tmp_path / "out")])

    assert code == 0
    assert commands
    assert all(command[0] == "git" for command in commands)

#!/usr/bin/env python3
"""Ekspor arsip riwayat AutoOffice dari tag git secara offline.

Eksportir membuat bundel seluruh ref, menyalin log eksekusi persis seperti pada
tag, membangun peta riwayat berbasis file, menyalin berkas pendukung bila
tersedia, lalu menulis SHA256SUMS. Semua langkah kecuali ``--upload`` berjalan
lokal tanpa jaringan.

Pemakaian:
    uv run python tools/history/export_archive.py --tag v1.0.0
    uv run python tools/history/export_archive.py --tag v1.0.0 --out dist/arsip
    uv run python tools/history/export_archive.py --tag v1.0.0 --upload

Kode keluar 0 bila arsip lengkap, 1 bila ekspor gagal, dan 2 bila argumen atau
tag tidak valid.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

LOG_PATH = "AUTO_OFFICE_EXECUTION_LOG.md"
CHECKSUM_NAME = "SHA256SUMS"
OPTIONAL_FILES: tuple[str, ...] = (
    "docs/dev/agent-rules.md",
    "archive/autooffice-history/lessons.jsonl",
    "archive/autooffice-history/eval-cases.md",
)
FILE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".bib",
        ".bundle",
        ".cfg",
        ".css",
        ".docx",
        ".fntdata",
        ".html",
        ".ini",
        ".js",
        ".json",
        ".jsonl",
        ".lock",
        ".md",
        ".png",
        ".pptx",
        ".ps1",
        ".py",
        ".sh",
        ".svg",
        ".toml",
        ".tsv",
        ".txt",
        ".yaml",
        ".yml",
    }
)
SECTION_PATTERN = re.compile(r"^## (?P<date>\d{4}-\d{2}-\d{2}) - (?P<title>.+?)\s*$")
BACKTICK_PATTERN = re.compile(r"`([^`\n]+)`")
SAFE_PATH_PATTERN = re.compile(r"^[\w@+./-]+$")


class ArchiveError(Exception):
    """Kegagalan ekspor yang menghentikan proses dengan kode 1."""


class UsageError(ArchiveError):
    """Argumen atau tag tidak valid; proses berhenti dengan kode 2."""


@dataclass(frozen=True)
class Section:
    """Satu bagian log dengan tanggal, judul, dan isi."""

    date: str
    title: str
    body: str


@dataclass(frozen=True)
class EntryMap:
    """Pemetaan satu entri log ke berkas dan commit yang menyentuhnya."""

    index: int
    date: str
    title: str
    paths: tuple[str, ...]
    commits: tuple[tuple[str, int], ...]


def run_command(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
    """Jalankan perintah tanpa shell dan kembalikan hasil mentah."""
    try:
        return subprocess.run(command, cwd=cwd, capture_output=True, check=False)
    except OSError as exc:
        raise ArchiveError(f"gagal menjalankan {command[0]}: {exc}") from exc


def _decode(data: bytes) -> str:
    """Ubah keluaran git menjadi teks yang aman ditampilkan."""
    return data.decode("utf-8", errors="replace").strip()


def _git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    """Jalankan git di dalam repositori tanpa mengubah state."""
    return run_command(["git", *arguments], repo)


def _git_stdout(repo: Path, *arguments: str, context: str) -> str:
    """Ambil stdout git atau hentikan ekspor dengan pesan konteks."""
    completed = _git(repo, *arguments)
    if completed.returncode != 0:
        detail = _decode(completed.stderr) or _decode(completed.stdout)
        raise ArchiveError(f"{context}: {detail}")
    return _decode(completed.stdout)


def _repo_root() -> Path:
    """Temukan akar repositori dari direktori kerja saat ini."""
    completed = run_command(["git", "rev-parse", "--show-toplevel"], Path.cwd())
    if completed.returncode != 0:
        raise ArchiveError("direktori kerja bukan repositori git")
    root = _decode(completed.stdout)
    if not root:
        raise ArchiveError("git tidak mengembalikan akar repositori")
    return Path(root).resolve()


def _require_tag(repo: Path, tag: str) -> None:
    """Pastikan tag ada; tag yang hilang adalah kesalahan pemakaian."""
    completed = _git(repo, "rev-parse", "--verify", f"refs/tags/{tag}")
    if completed.returncode != 0:
        raise UsageError(f"tag tidak ditemukan: {tag}")


def _tag_commit(repo: Path, tag: str) -> str:
    """Kembalikan hash pendek commit yang ditunjuk tag."""
    return _git_stdout(
        repo,
        "rev-parse",
        "--short",
        f"{tag}^{{commit}}",
        context=f"commit tag {tag} tidak dapat dibaca",
    )


def parse_log(text: str) -> tuple[Section, ...]:
    """Pisahkan log menjadi bagian berdasarkan judul bertanggal."""
    sections: list[Section] = []
    date = ""
    title = ""
    body: list[str] = []
    for line in text.splitlines():
        match = SECTION_PATTERN.match(line)
        if match is not None:
            if date:
                sections.append(Section(date, title, "\n".join(body)))
            date = match.group("date")
            title = match.group("title").strip()
            body = []
            continue
        if line.startswith("## "):
            if date:
                sections.append(Section(date, title, "\n".join(body)))
                date = ""
                title = ""
                body = []
            continue
        if date:
            body.append(line)
    if date:
        sections.append(Section(date, title, "\n".join(body)))
    return tuple(sections)


def _looks_like_path(token: str) -> bool:
    """True bila token berbentuk path relatif yang mungkin ada di repo."""
    if not token or "*" in token:
        return False
    if token == "." or token.startswith("..") or "/../" in token:
        return False
    if SAFE_PATH_PATTERN.fullmatch(token) is None:
        return False
    if "/" in token:
        return True
    if token.startswith("."):
        return True
    return Path(token).suffix.lower() in FILE_SUFFIXES


def extract_paths(body: str) -> tuple[str, ...]:
    """Ambil path unik dari teks berkutip balik, lewati pola glob."""
    paths: dict[str, None] = {}
    for match in BACKTICK_PATTERN.finditer(body):
        token = match.group(1).strip()
        if _looks_like_path(token):
            paths.setdefault(token, None)
    return tuple(paths)


def _commits_for_path(repo: Path, tag: str, path: str) -> tuple[str, ...]:
    """Daftar hash commit yang menyentuh satu path pada riwayat tag."""
    completed = _git(repo, "log", "--format=%h", tag, "--", path)
    if completed.returncode != 0:
        raise ArchiveError(f"riwayat commit untuk {path} tidak dapat dibaca")
    return tuple(line.strip() for line in _decode(completed.stdout).splitlines() if line.strip())


def build_entries(repo: Path, tag: str, sections: Sequence[Section]) -> tuple[EntryMap, ...]:
    """Petakan setiap bagian log ke berkas dan commit yang menyentuhnya."""
    entries: list[EntryMap] = []
    cache: dict[str, tuple[str, ...]] = {}
    for index, section in enumerate(sections, start=1):
        hits: dict[str, int] = {}
        mapped: list[str] = []
        for path in extract_paths(section.body):
            if path not in cache:
                cache[path] = _commits_for_path(repo, tag, path)
            commits = cache[path]
            if not commits:
                continue
            mapped.append(path)
            for commit in commits:
                hits[commit] = hits.get(commit, 0) + 1
        ordered = tuple(sorted(hits.items(), key=lambda item: (-item[1], item[0])))
        entries.append(EntryMap(index, section.date, section.title, tuple(mapped), ordered))
    return tuple(entries)


def _escape_cell(value: str) -> str:
    """Lindungi teks agar tidak merusak kolom tabel Markdown."""
    return value.replace("|", "\\|").replace("\n", " ")


def render_history_map(tag: str, tag_commit: str, entries: Sequence[EntryMap]) -> str:
    """Render peta riwayat Markdown dari hasil pemetaan file."""
    lines = [
        "# Peta Riwayat AutoOffice",
        "",
        f"Sumber: `{LOG_PATH}` pada tag `{tag}` (commit `{tag_commit}`).",
        "",
        "Pemetaan ini berbasis file: setiap entri dipetakan ke commit yang menyentuh "
        "berkas yang disebut pada entri tersebut. Tidak ada commit tunggal yang "
        "dianggap pemilik entri. Commit diurutkan menurut jumlah berkas entri yang "
        "disentuh, lalu hash.",
        "",
        "| Entri | Tanggal | File | Commit terkait | Perintah |",
        "| --- | --- | --- | --- | --- |",
    ]
    for entry in entries:
        files = "<br>".join(f"`{path}`" for path in entry.paths) or "-"
        commits = (
            "<br>".join(f"`{commit}` ({count} berkas)" for commit, count in entry.commits) or "-"
        )
        commands = (
            "<br>".join(f"`git log --format=%h {tag} -- {path}`" for path in entry.paths) or "-"
        )
        lines.append(
            f"| {entry.index}. {_escape_cell(entry.title)} | {entry.date} | {files} | "
            f"{commits} | {commands} |"
        )
    lines.extend(("", f"Jumlah entri: {len(entries)}.", ""))
    return "\n".join(lines)


def _read_at_tag(repo: Path, tag: str, path: str) -> bytes | None:
    """Baca blob pada tag; kembalikan None bila path tidak ada di tag."""
    kind = _git(repo, "cat-file", "-t", f"{tag}:{path}")
    if kind.returncode != 0 or _decode(kind.stdout) != "blob":
        return None
    completed = _git(repo, "show", f"{tag}:{path}")
    if completed.returncode != 0:
        raise ArchiveError(f"{path} tidak dapat dibaca pada tag {tag}")
    return completed.stdout


def _create_bundle(repo: Path, tag: str, destination: Path) -> None:
    """Buat bundel seluruh ref lalu pastikan verifikasinya lulus."""
    completed = _git(repo, "bundle", "create", str(destination), "--all")
    if completed.returncode != 0:
        detail = _decode(completed.stderr) or _decode(completed.stdout)
        raise ArchiveError(f"bundel gagal dibuat: {detail}")
    verified = _git(repo, "bundle", "verify", str(destination))
    report = _decode(verified.stdout + b"\n" + verified.stderr)
    if verified.returncode != 0:
        raise ArchiveError(f"bundel tidak lolos verifikasi: {report}")
    if f"refs/tags/{tag}" not in report:
        raise ArchiveError(f"bundel tidak memuat refs/tags/{tag}")


def _write_checksums(directory: Path) -> None:
    """Tulis SHA256SUMS deterministik untuk semua berkas di direktori."""
    files = sorted(
        (path for path in directory.iterdir() if path.is_file() and path.name != CHECKSUM_NAME),
        key=lambda path: path.relative_to(directory).as_posix(),
    )
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(directory).as_posix()}"
        for path in files
    ]
    destination = directory / CHECKSUM_NAME
    destination.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _verify_checksums(directory: Path) -> None:
    """Periksa ulang setiap baris SHA256SUMS terhadap isi direktori."""
    checksum_path = directory / CHECKSUM_NAME
    if not checksum_path.is_file():
        raise ArchiveError(f"{CHECKSUM_NAME} tidak ditemukan")
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise ArchiveError(f"baris {CHECKSUM_NAME} tidak valid: {line}")
        digest, name = parts
        target = directory / name
        if not target.is_file():
            raise ArchiveError(f"berkas checksum tidak ditemukan: {name}")
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ArchiveError(f"checksum tidak cocok: {name}")


def _produce(
    repo: Path, tag: str, tag_commit: str, staging: Path
) -> tuple[tuple[EntryMap, ...], tuple[str, ...]]:
    """Tulis semua keluaran ke direktori staging yang belum terlihat pengguna."""
    log_bytes = _read_at_tag(repo, tag, LOG_PATH)
    if log_bytes is None:
        raise ArchiveError(f"{LOG_PATH} tidak ada pada tag {tag}")
    (staging / LOG_PATH).write_bytes(log_bytes)
    _create_bundle(repo, tag, staging / f"autooffice-{tag}.bundle")
    try:
        log_text = log_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArchiveError(f"{LOG_PATH} bukan UTF-8: {exc}") from exc
    entries = build_entries(repo, tag, parse_log(log_text))
    (staging / "history-map.md").write_bytes(render_history_map(tag, tag_commit, entries).encode())
    copied: list[str] = []
    for source in OPTIONAL_FILES:
        source_path = repo / source
        if not source_path.is_file():
            continue
        destination = staging / source_path.name
        destination.write_bytes(source_path.read_bytes())
        copied.append(destination.name)
    _write_checksums(staging)
    _verify_checksums(staging)
    return entries, tuple(copied)


def _upload_release(repo: Path, tag: str, directory: Path, names: Sequence[str]) -> None:
    """Buat atau perbarui rilis GitHub tanpa membuat tag baru."""
    gh = shutil.which("gh")
    if gh is None:
        raise ArchiveError("gh tidak ditemukan di PATH")
    asset_names = [str(directory / name) for name in names]
    viewed = run_command([gh, "release", "view", tag], repo)
    if viewed.returncode == 0:
        command = [gh, "release", "upload", tag, "--clobber", *asset_names]
    else:
        notes = f"Arsip riwayat AutoOffice untuk tag {tag}."
        command = [
            gh,
            "release",
            "create",
            tag,
            "--title",
            tag,
            "--notes",
            notes,
            "--verify-tag",
            *asset_names,
        ]
    completed = run_command(command, repo)
    if completed.returncode != 0:
        detail = _decode(completed.stderr) or _decode(completed.stdout)
        raise ArchiveError(f"unggah rilis gagal: {detail}")


def export_archive(tag: str, out: str | None, upload: bool) -> Path:
    """Hasilkan arsip lengkap di direktori keluaran dan kembalikan path-nya."""
    repo = _repo_root()
    _require_tag(repo, tag)
    out_path = Path(out) if out else Path("dist") / f"history-{tag}"
    if not out_path.is_absolute():
        out_path = repo / out_path
    out_dir = out_path.resolve()
    if out_dir == repo or out_dir.is_relative_to(repo / ".git"):
        raise UsageError("direktori keluaran tidak boleh berada di akar repo atau di dalam .git")
    if out_dir.exists() and not out_dir.is_dir():
        raise ArchiveError(f"keluaran bukan direktori: {out_dir}")
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    tag_commit = _tag_commit(repo, tag)
    with tempfile.TemporaryDirectory(prefix=f".{out_dir.name}.", dir=out_dir.parent) as temporary:
        staging = Path(temporary)
        entries, copied = _produce(repo, tag, tag_commit, staging)
        staging_files = sorted(staging.iterdir(), key=lambda path: path.name)
        for source in staging_files:
            if not source.is_file():
                raise ArchiveError(f"keluaran tidak dikenal: {source.name}")
        out_dir.mkdir(parents=True, exist_ok=True)
        for source in staging_files:
            os.replace(source, out_dir / source.name)
    output_names = tuple(source.name for source in staging_files)
    _verify_checksums(out_dir)
    print(f"[arsip] tag: {tag} ({tag_commit})")
    print(f"[arsip] keluaran: {out_dir}")
    print(f"[arsip] bundel: autooffice-{tag}.bundle (verifikasi lulus)")
    print(f"[arsip] peta riwayat: {len(entries)} entri")
    for name in copied:
        print(f"[arsip] salinan: {name}")
    print(f"[arsip] checksum: {CHECKSUM_NAME}")
    if upload:
        _upload_release(repo, tag, out_dir, output_names)
        print("[arsip] unggah: selesai")
    else:
        print("[arsip] unggah: dilewati (tanpa --upload)")
    return out_dir


def _print_tags(repo: Path) -> None:
    """Cetak tag yang tersedia dalam urutan deterministik."""
    completed = _git(repo, "tag", "--list", "--sort=refname")
    if completed.returncode != 0:
        raise ArchiveError("daftar tag tidak dapat dibaca")
    tags = [line for line in _decode(completed.stdout).splitlines() if line]
    if not tags:
        print("Tidak ada tag.")
        return
    print("Tag tersedia:")
    for tag in tags:
        print(f"- {tag}")


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser CLI tanpa menjalankan ekspor."""
    parser = argparse.ArgumentParser(
        prog="export_archive.py",
        description="Ekspor arsip riwayat AutoOffice dari tag git secara offline.",
        epilog=(
            "Contoh: uv run python tools/history/export_archive.py "
            "--tag v1.0.0 --out dist/history-v1.0.0"
        ),
    )
    parser.add_argument(
        "--tag",
        metavar="TAG",
        help="tag git yang diarsipkan; wajib kecuali memakai --list",
    )
    parser.add_argument(
        "--out",
        metavar="DIR",
        help="direktori keluaran; default dist/history-<tag>",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="unggah hasil ke rilis GitHub setelah checksum lulus; tanpa tag baru",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_tags",
        help="cetak tag yang tersedia lalu keluar",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Jalankan CLI dan kembalikan kode keluar 0, 1, atau 2."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_tags:
        try:
            _print_tags(_repo_root())
        except ArchiveError as exc:
            print(f"[arsip] gagal: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.tag is None:
        parser.error("--tag wajib diisi kecuali memakai --list")
    if "/" in args.tag or "\\" in args.tag:
        parser.error("--tag tidak boleh memuat pemisah path")
    try:
        export_archive(args.tag, args.out, args.upload)
    except UsageError as exc:
        print(f"[arsip] gagal: {exc}", file=sys.stderr)
        return 2
    except (ArchiveError, OSError) as exc:
        print(f"[arsip] gagal: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    raise SystemExit(main(sys.argv[1:]))

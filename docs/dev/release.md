# Rilis

Prosedur ini menghasilkan satu rilis AutoOffice: commit `chore: release X.Y.Z`,
annotated tag `vX.Y.Z`, dan arsip sejarah yang tidak boleh ditulis ulang.
Invarian proyek ada di [AGENTS.md](../../AGENTS.md); aturan agent ada di
[agent-rules.md](agent-rules.md).

## Prasyarat

- Branch `main` bersih dan sudah memuat seluruh perubahan rilis.
- Tidak ada branch kerja yang belum di-merge.
- `uv` dan `gh` tersedia; `gh auth status` lulus bila memakai `--upload`.
- Nomor versi belum dipakai tag lain: `git tag --list "vX.Y.Z"` harus kosong.

## 1. Gate pra-rilis

```bash
uv run python tools/quality/gate.py
uv build
uv run pytest tests/packaging/test_wheel_contents.py -m slow -q
git diff --check
git status --short
```

Gate harus lulus penuh. `git status --short` harus kosong sebelum bump versi.
Jangan lanjut bila ada langkah yang gagal.

## 2. Bump versi

Ubah versi di dua tempat:

- `pyproject.toml` pada `[project].version`;
- `src/autooffice/__init__.py` pada `__version__`.

Keduanya harus bernilai `X.Y.Z`. Setelah itu perbarui lock:

```bash
uv lock
```

Jangan mengedit `uv.lock` manual. Pastikan `uv lock --check` masih lulus.

## 3. Commit rilis

```bash
git add pyproject.toml src/autooffice/__init__.py uv.lock
git commit -m "chore: release X.Y.Z"
```

Commit ini hanya berisi bump versi dan lock. Perubahan fitur masuk commit
terpisah sebelum commit rilis.

## 4. Tag anotasi

```bash
git tag -a vX.Y.Z -m "AutoOffice X.Y.Z"
```

Satu tag per rilis. Jangan memindahkan, menghapus, atau membuat ulang tag yang
sudah di-push.

## 5. Push

```bash
git push origin main
git push origin vX.Y.Z
```

Push tag setelah commit rilis terkirim. Jangan push tag dari commit lain.

## 6. Ekspor dan unggah arsip

```bash
uv run python tools/history/export_archive.py --tag vX.Y.Z
uv run python tools/history/export_archive.py --tag vX.Y.Z --upload
```

Perintah pertama menulis arsip ke `dist/history-<tag>`; gunakan `--out DIR`
untuk lokasi lain. `--upload` membuat GitHub release `vX.Y.Z` dan mengunggah
aset yang checksum-nya sudah lulus. Jangan mengulang `--upload` untuk tag yang
sudah dirilis. Catat tag, commit, tanggal, dan checksum di
`archive/autooffice-history/README.md`.

## Aset rilis

- `autooffice-<tag>.bundle`: git bundle seluruh ref sampai tag, lolos
  `git bundle verify`, dan memuat `refs/tags/<tag>`.
- `AUTO_OFFICE_EXECUTION_LOG.md`: salinan log persis seperti pada tag.
- `history-map.md`: peta entri log ke berkas dan commit terkait.
- `SHA256SUMS`: checksum SHA-256 untuk semua berkas di direktori arsip.
- Bila ada pada tag: `agent-rules.md`, `lessons.jsonl`, dan `eval-cases.md`.

Wheel bukan aset rilis resmi; jalur distribusi yang diuji adalah repo-local,
lihat [packaging.md](packaging.md).

## Restore dari arsip

```bash
git clone autooffice-vX.Y.Z.bundle autooffice-vX.Y.Z
cd autooffice-vX.Y.Z
git checkout vX.Y.Z
git fsck --full
uv sync --extra dev
uv run autooffice --version
```

`git clone` dari bundle memulihkan history dan tag. Setelah restore, jalankan
gate penuh sebelum memakai hasil restore untuk perubahan baru.

## Aturan arsip

- Arsip yang sudah dirilis tidak pernah ditulis ulang, diganti, atau dihapus.
- Jangan membuat ulang tag atau aset dengan nama yang sama. Koreksi rilis
  dilakukan dengan rilis baru `vX.Y.(Z+1)`.
- Tag `pre-pdf-removal` dan `backup/main-before-msg-rewrite` permanen dan tidak
  boleh dihapus.

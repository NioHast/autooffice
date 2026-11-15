# Opsi Build

Halaman ini menjelaskan flag `autooffice build` dan matriks target. Kontrak
CLI ada di [contracts/cli.md](../../contracts/cli.md).

## Opsi build

| Flag | Berlaku | Arti |
| --- | --- | --- |
| `--target` | wajib | Target dipisah koma: `docx` untuk `.md`; `pptx` atau `slides` untuk `.yaml`. |
| `--out DIR` | semua | Direktori output final; harus direktori, bukan berkas. |
| `--theme NAME` | `.yaml` | `indigo` atau `hitam`; menimpa `theme.name`. |
| `--terms` | `.md` | Aktifkan check, apply, verify, dan review istilah. |
| `--dry-run` | semua | Validasi penuh dan cetak rencana tanpa menulis output, state, atau remote. |
| `--keep-intermediate` | semua | Pertahankan workspace dan intermediate DOCX/PPTX/staging. |
| `--sync MODE` | `.yaml` + `slides` | `push` (default), `pull`, `diff`, atau `apply`. |

Tidak ada target `pdf` atau `all`.

## Aturan target

| Input | `docx` | `pptx` | `slides` |
| --- | --- | --- | --- |
| `.md` | ya | tidak | tidak |
| `.yaml` | tidak | ya | ya |

- Target dipisah koma; spasi setelah koma boleh.
- Duplikat dihapus dan urutan kanonik dipertahankan.
- `slides` memerlukan extra `google` dan kredensial OAuth. Tutorial ada di
  [google-oauth.md](../../user/google-oauth.md).
- `pptx` adalah jalur offline untuk deck.
- DOCX memakai field native yang tidak diisi otomatis. Pengguna membuka DOCX
  di Word, menekan Ctrl+A lalu F9, sebelum review atau ekspor PDF.

## Target per platform

| Platform | `docx` | `pptx` | `slides` |
| --- | --- | --- | --- |
| Windows | ya | ya | ya dengan Google OAuth |
| Linux/macOS | ya | ya | ya dengan Google OAuth |

Build DOCX dan PPTX tidak memerlukan Office, COM, `pywin32`, atau font yang
terpasang. PPTX memakai Arial tanpa embedding; layout diukur dengan Liberation
Sans yang metrik-kompatibel Arial. Diagram memerlukan PlantUML 1.2026.10 atau
lebih baru dan Java 21; tidak ada Node.js, Chromium, atau Graphviz. PDF diekspor
manual dari Word atau PowerPoint; lihat
[Ekspor PDF Manual](../../user/pdf-export.md).

## Referensi resmi

Label registry yang dipakai halaman ini: `Pandoc manual` dan `PlantUML command
line`. URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [stages.md](stages.md) untuk stage yang diaktifkan `--terms`.
- [outputs.md](outputs.md) untuk nama dan lokasi artefak.
- [artifacts.md](artifacts.md) untuk efek `--keep-intermediate`.
- [errors.md](errors.md) untuk kegagalan target.
- [design system](../../learn/design-system.md) untuk Arial dan pengukuran.

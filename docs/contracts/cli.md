# Kontrak CLI

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 10 (10.1-10.11), 13.2, dan keputusan L16.
Pemilik kontrak: integration owner.

## Tujuan

Kontrak ini membekukan satu permukaan perintah `autooffice`: nama perintah,
matriks target, penamaan output, exit code, dan aturan error. Permukaan di
bawah ini adalah permukaan final v1. Tidak ada permukaan kedua, alias, shim,
atau entry point baru.

## Invarian

1. Perintah yang diizinkan hanya:

```text
autooffice build <input> --target <targets> [opsi]
autooffice check <input> [opsi]
autooffice doctor [opsi]
autooffice --version
autooffice --help
```

2. Permukaan final v1 tidak punya perintah, alias, shim, atau entry point
   selain yang di atas. Nama package dan entry point lama tidak dipertahankan.
   `--help` hanya menampilkan perintah yang didukung.
3. `--target` wajib untuk `build`. Target dipisah koma, spasi setelah koma
   boleh, duplikat dihapus, dan urutan kanonik dipertahankan.
4. Tidak ada target `pdf` atau `all`. Target hanya `docx` untuk `.md` serta
   `pptx` dan `slides` untuk `.yaml`.
5. Input selain `.md` dan `.yaml` ditolak. `docx` hanya untuk `.md`; `pptx`
   dan `slides` hanya untuk `.yaml`.

`tools/quality/check_no_legacy.py` memeriksa path, import, entry point, dan
nama teknologi legacy. Gate memanggilnya sebagai langkah blocking; allowlist
eksplisit mencakup arsip, ADR, fixture golden, dan guard negatif.

## Matriks target

| Input | `docx` | `pptx` | `slides` |
| --- | --- | --- | --- |
| `.md` | ya | tidak | tidak |
| `.yaml` | tidak | ya | ya |

- `slides` memerlukan extra `google` dan kredensial OAuth.
- `pptx` adalah jalur offline untuk deck.
- DOCX memakai field native yang tidak diisi otomatis. Pengguna membuka DOCX
  di Word, menekan Ctrl+A lalu F9, sebelum review atau ekspor PDF.
- PDF diekspor manual dari Word atau PowerPoint; tidak ada target PDF.

## Flag

| Flag | Berlaku | Aturan |
| --- | --- | --- |
| `--out DIR` | semua | Direktori output, dibuat bila belum ada; tidak boleh menunjuk file. |
| `--theme NAME` | `.yaml` | `indigo` atau `hitam`; menimpa `theme.name`; error untuk `.md`. |
| `--terms` | `.md` | Menulis daftar istilah baru seperti pipeline DOCX baseline; error untuk `.yaml`. |
| `--dry-run` | semua | Validasi penuh dan cetak rencana; tidak menulis output, state, atau remote. |
| `--keep-intermediate` | semua | Menyimpan intermediate di lokasi yang didokumentasikan. |
| `--sync MODE` | `.yaml` + `slides` | `push` (default), `pull`, `diff`, `apply`. |

`--sync` hanya valid bila target berisi `slides`. `pull`, `diff`, dan `apply`
memerlukan state dengan `presentation_id`.

## Penamaan output

Input `.md` mengikuti perilaku baseline DOCX:

- `<report_name>.docx` dari front matter.
- Manifest `.laporan/manifest.json`.
- Istilah `.laporan/istilah-baru.txt`.
- Intermediate `.laporan-build/`.
- `examples/<name>/document.md` default ke `examples/<name>/out/`.
- `--out DIR` hanya menimpa direktori output final. Manifest, istilah, dan
  intermediate `.laporan-build/` tetap berada di samping dokumen sumber.

Input `.yaml`:

- Output default di samping YAML, kecuali `examples/<name>/` memakai
  `examples/<name>/out/`.
- `<stem>.pptx` dan `<stem>.transcript.md` bila `transcripts.md` ada.
- Staging internal `<stem>.slides-upload.pptx`, bukan deliverable.
- State `.autooffice/state/<stem>.json`, cache `.autooffice/cache/`,
  intermediate `.autooffice-build/<stem>/`, dan review `.autooffice/review/`.
- `--out DIR` mengubah direktori artefak final saja. State, cache,
  intermediate, dan review tetap berada di samping YAML agar pembersihan
  intermediate tidak pernah menyentuh direktori output.

## Dry-run dan penulisan

`--dry-run` wajib memvalidasi input dan aset, menjalankan copy checker dan
transcript validation, menyusun compiler, layout measurement, coverage plan,
serta mencetak file, target, aksi Google, dan rencana diff. Dry-run juga
memvalidasi API lane yang diperlukan (renderer PPTX dan operasi Google) tanpa
memanggil Office atau jaringan. Dry-run tidak menulis file atau state dan
tidak menulis ke Drive, Sheets, atau Slides. Temuan overflow, key hilang, atau
kredensial Google yang tidak ada saat target Slides menghasilkan exit code
nonzero.

File final ditulis atomik. Output yang sudah selesai tidak dihapus saat target
lain gagal, tetapi exit code tetap nonzero dan ringkasan diberikan.

## Exit code

| Kode | Arti |
| --- | --- |
| 0 | Sukses; `diff` dengan perbedaan tetap 0 karena operasi diff berhasil. |
| 1 | Validasi, build, coverage, dependency, Google, atau temuan check. |
| 2 | Argumen CLI salah, target tidak valid, atau kombinasi flag salah. |

Error validasi menyebut input, slide, block, key, dan field. Error aset
menyebut path relatif dan path absolut hasil resolusi. Error Google menyebut
operasi, file, dan langkah. Tidak ada traceback panjang kecuali environment
debug eksplisit dan tidak ada fallback diam-diam.

## Contoh

```bash
autooffice build examples/demo-deck/deck.yaml --target pptx --out out
autooffice build examples/demo-deck/deck.yaml --target slides --sync diff
autooffice check examples/thesis-single/document.md
```

Perintah pertama menulis `out/deck.pptx` tanpa memanggil Google. Perintah
kedua hanya membaca remote dan menulis laporan diff di
`.autooffice/review/`.

## Pemetaan acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Invarian | Bukti |
| --- | --- |
| Permukaan final v1 | `autooffice --help`; `tests/cli/test_cli.py`; `tests/cli/test_targets.py`. |
| Pemeriksaan teknologi legacy dan fitur dihapus | `tools/quality/check_no_legacy.py`; `tools/quality/check_removed_features.py`; langkah gate `no-legacy` dan `removed-features`. |
| Matriks target dan normalisasi | `tests/cli/test_targets.py`; acceptance bagian 18.8. |
| Penamaan output dan `--out` | `tests/cli/test_outputs.py`; golden output. |
| Exit code dan error | `tests/cli/test_cli.py`; `tests/cli/test_build_markdown.py`; contract test pesan error. |
| Dry-run tanpa efek samping | `tests/cli/test_build_deck.py`; fake Google. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)

# CLI AutoOffice

`autooffice` adalah satu-satunya permukaan perintah AutoOffice. Tidak ada alias,
shim, atau entry point kedua. Kontrak normatifnya ada di
[kontrak CLI](../contracts/cli.md).

## Perintah

```text
autooffice build <input> --target <targets> [opsi]
autooffice check <input> [opsi]
autooffice doctor [opsi]
autooffice --version
autooffice --help
```

`autooffice` tanpa perintah menampilkan bantuan dan keluar dengan kode 0.

## Target

| Input | `docx` | `pptx` | `slides` |
| --- | --- | --- | --- |
| `.md` | ya | tidak | tidak |
| `.yaml` | tidak | ya | ya |

- Target dipisah koma dan spasi setelah koma boleh.
- Duplikat dihapus dan urutan kanonik dipakai: `docx` untuk `.md`, lalu
  `pptx,slides` untuk `.yaml`.
- `--target` wajib untuk `build`.
- Tidak ada target `pdf` atau `all`.
- `slides` untuk `.yaml` memerlukan extra `google` serta kredensial OAuth.
  Jalur offline untuk deck adalah `pptx`.
- Input selain `.md` dan `.yaml` ditolak.
- DOCX memakai field native yang tidak diisi otomatis. Pengguna membuka DOCX
  di Word, menekan Ctrl+A lalu F9, sebelum review atau ekspor PDF.
- PDF diekspor manual dari Word atau PowerPoint; lihat
  [pdf-export.md](pdf-export.md).

## Penamaan output

### Input `.md`

- `<report_name>.docx` dari front matter.
- Manifest `.laporan/manifest.json` dan istilah `.laporan/istilah-baru.txt`
  tetap berada di samping dokumen sumber.
- Intermediate `.laporan-build/`.
- `examples/<nama>/document.md` menulis final ke `examples/<nama>/out/`;
  dokumen pengguna menulis di direktori dokumen.
- `--out DIR` hanya memindahkan artefak final.

### Input `.yaml`

- `<stem>.pptx` dan `<stem>.transcript.md` bila `transcripts.md` ada.
- Staging internal `<stem>.slides-upload.pptx`.
- State `.autooffice/state/<stem>.json`, cache `.autooffice/cache/`, review
  `.autooffice/review/`, dan intermediate `.autooffice-build/<stem>/`.
- `--out DIR` hanya memindahkan artefak final. State, cache, intermediate,
  dan review tetap di samping YAML agar pembersihan workspace aman.
- Mode `--sync diff|pull|apply` tidak merender dan tidak membuat workspace;
  mode tersebut juga tidak menghapus `.autooffice-build/<stem>/` yang sudah
  ada, termasuk intermediate yang dipertahankan `--keep-intermediate`.

## Flag

| Flag | Berlaku | Arti |
| --- | --- | --- |
| `--out DIR` | semua | Direktori output final; harus direktori, bukan berkas. |
| `--theme NAME` | `.yaml` | `indigo` atau `hitam`; menimpa `theme.name`. |
| `--terms` | `.md` | Menjalankan gate istilah seperti pipeline DOCX lama. |
| `--dry-run` | semua | Validasi dan cetak rencana tanpa menulis file final, state, atau remote. |
| `--keep-intermediate` | semua | Menyimpan intermediate di lokasi yang terdokumentasi; tanpa flag ini workspace dibersihkan setelah build selesai. |
| `--sync MODE` | `.yaml` + `slides` | `push` (default), `pull`, `diff`, atau `apply`. |

`--theme` untuk `.md`, `--terms` untuk `.yaml`, dan `--sync` tanpa target
`slides` ditolak dengan kode keluar 2.

## Dry-run

`--dry-run` memvalidasi input, aset, copy checker, transkrip, compiler,
layout, dan coverage plan. Dry-run mencetak target yang dijalankan serta file
yang akan ditulis, tetapi tidak menulis file atau state dan tidak menulis ke
Drive, Sheets, atau Slides. Overflow, key hilang, atau dependency wajib yang
tidak tersedia menghasilkan kode keluar nonzero.

## Check dan doctor

`autooffice check <input>` tidak memanggil Pandoc atau Google.

- `.md`: front matter, format, struktur, aset, urutan heading, dan caption.
- `.yaml`: schema, compiler, coverage plan, layout/overflow, copy checker, dan
  transcript validation bila modul dan berkasnya tersedia.

`autooffice doctor` memeriksa Python, Pandoc, PlantUML, integritas aset font
pengukuran Liberation Sans, extra Google, kredensial OAuth lokal, dan izin
tulis workspace tanpa jaringan. Tambahkan `--json` untuk keluaran mesin yang
deterministik. `doctor` tetap berjalan tanpa extra `google`; pemeriksaan
Google dilaporkan belum terpasang dan pemeriksaan lain tetap dijalankan.
Target `slides` mewajibkan token Google. Tidak ada pemeriksaan Word,
PowerPoint, COM, atau `pywin32`.

Pemeriksaan `plantuml` melaporkan path dan versi engine. Diagram memerlukan
Java 21 dan PlantUML 1.2026.10 atau lebih baru; rinciannya ada di
[plantuml.md](plantuml.md).

## Font PPTX

Target `pptx` memakai family `Arial`. AutoOffice tidak menanam font ke PPTX
dan tidak memerlukan font terpasang di mesin build. Layout diukur dengan
Liberation Sans, font metrik-kompatibel Arial, sehingga ukuran dan posisi
konsisten dengan Arial.

Di Android, Linux, atau lingkungan tanpa Arial, aplikasi dapat mengganti
Arial dengan Liberation Sans atau font substitusi lain. Tata letak umumnya
tetap sama, tetapi bentuk glyph dan rendering dapat berbeda. Bila PDF harus
tampil identik di semua perangkat, aktifkan embedding font saat mengekspor
dari Word atau PowerPoint. AutoOffice tidak menyediakan installer font.

## Kode keluar

| Kode | Arti |
| --- | --- |
| 0 | Sukses atau `check` tanpa temuan. |
| 1 | Validasi, build, coverage, dependency, Google, atau temuan check. |
| 2 | Argumen CLI salah, target tidak valid, atau kombinasi flag salah. |

## Contoh

```bash
autooffice build document.md --target docx
autooffice build document.md --target docx --terms
autooffice build deck.yaml --target pptx
autooffice build deck.yaml --target pptx --dry-run
autooffice build deck.yaml --target slides --sync diff
autooffice check document.md
autooffice check deck.yaml --target pptx
autooffice doctor --json
```

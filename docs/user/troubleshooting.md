# Troubleshooting

Jalankan perintah `doctor` lebih dulu untuk memisahkan masalah perkakas dari
masalah naskah:

```bash
uv run --project <repo> autooffice doctor
```

Perintah itu memeriksa Python, Pandoc, PlantUML, integritas aset font pengukuran
Liberation Sans, extra Google, kredensial OAuth, dan izin tulis workspace.
Exit code 1 berarti dependensi wajib belum lengkap. AutoOffice tidak memeriksa
Word, PowerPoint, COM, atau `pywin32`.

## Daftar isi

- [Caption tabel atau gambar](#caption-tabel-atau-gambar)
- [PlantUML tidak ditemukan atau gagal render](#plantuml-tidak-ditemukan-atau-gagal-render)
- [Pandoc tidak ditemukan](#pandoc-tidak-ditemukan)
- [Python terlalu lama](#python-terlalu-lama)
- [`ruamel.yaml` atau YAML tidak valid](#ruamelyaml-atau-yaml-tidak-valid)
- [Word atau PDF](#word-atau-pdf)
- [Linux dan macOS](#linux-dan-macos)
- [Path dan aset](#path-dan-aset)
- [Output terkunci atau gagal ditulis](#output-terkunci-atau-gagal-ditulis)
- [Istilah dan review file](#istilah-dan-review-file)
- [Bantuan lanjutan](#bantuan-lanjutan)

## Caption tabel atau gambar

Gejala:

```text
caption Markdown tidak valid:
- document.md:14: tabel tanpa caption; tambahkan baris ': Judul tabel'
- document.md:22: gambar tanpa alt text; tulis ![deskripsi gambar](path)
```

Tindakan:

1. Tambahkan baris `: Judul tabel` sebelum atau sesudah tabel.
2. Ganti `![](gambar/x.png)` menjadi `![Deskripsi gambar](gambar/x.png)`.
3. Jalankan ulang `check`.
4. Build ulang.

Jangan menambahkan caption kosong atau nomor manual. Nomor caption dibuat dari
Heading 1 dan urutan tabel/gambar.

## PlantUML tidak ditemukan atau gagal render

Gejala:

```text
PlantUML tidak ditemukan di PATH. (PLANTUML-TOOL)
Java tidak ditemukan untuk menjalankan PlantUML plantuml.jar. (PLANTUML-JAVA)
PlantUML 1.2025.9 terlalu lama; butuh PlantUML 1.2026.10 atau lebih baru. (PLANTUML-VERSION)
```

Tindakan:

1. Pasang Java 21 dan pastikan `java -version` berhasil dari shell yang sama.
2. Unduh `plantuml-1.2026.10.jar`, atau pasang executable `plantuml`.
3. Set `AUTOOFFICE_PLANTUML` ke path jar atau executable. Bila memakai jar dan
   `java` tidak ada di `PATH`, set `AUTOOFFICE_JAVA`.
4. Jalankan `uv run autooffice doctor` dan periksa baris `plantuml`.
5. Build ulang.

AutoOffice tidak membutuhkan Node.js, `npm`, Chromium, atau Graphviz. Jangan
memasang salah satu dari itu untuk memperbaiki render. Bila error
berkode `PLANTUML-SYNTAX`, perbaiki sintaks `.puml`; PlantUML tidak menulis
gambar error. Bila error berkode `PLANTUML-INPUT`, periksa `caption` dan fence
DOCX. Bila error menyebut `!include`, salin isi yang dibutuhkan ke dalam
diagram karena `-secure` menolak akses berkas.

## Pandoc tidak ditemukan

Gejala:

```text
Pandoc tidak ditemukan; build DOCX tidak dapat dilanjutkan.
```

Tindakan:

1. Pasang Pandoc; lihat label `Pandoc installation` di
   [registry referensi](../dev/references.md).
2. Pastikan `pandoc --version` berhasil dari shell yang sama.
3. Jalankan `doctor` lagi.

Pipeline mencari `pandoc` di `PATH`, lalu di lokasi instalasi Windows yang
umum. Variabel `DOCGEN_PANDOC` atau `PANDOC` dapat menunjuk executable
eksplisit.

## Python terlalu lama

Gejala:

```text
Python 3.14.x (butuh >=3.15)
```

Tindakan:

```bash
uv python install 3.15
uv sync --extra dev
```

`pyproject.toml` mensyaratkan Python 3.15. `uv run --project <repo>` memakai
environment proyek dan tidak memakai Python global secara diam-diam.

## `ruamel.yaml` atau YAML tidak valid

Gejala:

- `ModuleNotFoundError: No module named 'ruamel'`
- `front matter tidak valid`
- `kunci YAML duplikat`

Tindakan:

```bash
uv sync --project <repo> --extra dev
```

Periksa juga:

- berkas harus UTF-8;
- front matter dimulai `---` di baris pertama dan ditutup `---`;
- gunakan spasi, bukan tab;
- jangan memakai anchor, alias, atau merge key;
- jangan menulis kunci duplikat.

## Word atau PDF

DOCX hasil build memakai field native. AutoOffice tidak memperbarui field,
tidak mengisi daftar isi, dan tidak mengekspor PDF.

Gejala:

- daftar isi atau daftar tabel kosong;
- nomor halaman daftar isi masih `0` atau memakai cache lama;
- PDF belum ada setelah build.

Tindakan:

1. Buka DOCX hasil build di Microsoft Word.
2. Pilih seluruh dokumen dengan Ctrl+A, lalu tekan F9. Untuk daftar isi,
   pengguna juga dapat memakai References > Update Table.
3. Periksa nomor halaman, caption, dan page break.
4. Ekspor PDF manual dari Word: File > Save As atau File > Export > Create
   PDF/XPS.

Tidak ada target `pdf` atau `all`. Build tidak memanggil Word, PowerPoint,
COM, atau `pywin32`. Alur ekspor lengkap ada di [pdf-export.md](pdf-export.md).

## Linux dan macOS

Di Linux dan macOS, DOCX dan PPTX dapat dibangun tanpa Word, PowerPoint, COM,
atau `pywin32`. Field DOCX tetap belum final sampai pengguna membuka DOCX di
Word dan menekan Ctrl+A lalu F9. PDF diekspor manual dari Word atau PowerPoint.

Build tidak membutuhkan Office desktop dan tidak memiliki jalur PDF tersembunyi.

## Path dan aset

- Gunakan pemisah `/`, termasuk di Windows.
- Path absolut, `..`, backslash, URL, dan data URI ditolak.
- Gambar harus berada di dalam direktori dokumen, biasanya `gambar/`.
- Sumber diagram deck harus berupa `.puml` dan berada di dalam direktori
  `deck.yaml`.
- Bibliografi harus berekstensi `.bib` dan berada di direktori dokumen atau
  subdirektori.
- Bungkus path berspasi dengan tanda kutip di shell.
- Jalankan `check` setelah memindahkan berkas.

Gejala umum:

```text
berkas tidak ditemukan: gambar/diagram.png
path 'gambar' keluar dari direktori dokumen
bibliography harus berekstensi .bib
```

## Output terkunci atau gagal ditulis

Gejala:

```text
Permission denied
file is being used by another process
```

Tindakan:

1. Tutup Word, LibreOffice, atau PDF viewer yang membuka berkas output. DOCX
   mengikuti `report_name`, misalnya `Tugas.docx`. PDF manual dapat terkunci
   bila sedang dibuka saat pengguna mengekspor ulang.
2. Pastikan direktori dokumen dapat ditulis.
3. Build ulang.

Pipeline menulis output DOCX secara atomic. Kegagalan tidak boleh meninggalkan
DOCX setengah jadi di direktori tujuan. PDF adalah hasil ekspor manual dan
tidak ditulis oleh pipeline.

## Istilah dan review file

Dengan `--terms`, hasil review ditulis ke `.laporan/istilah-baru.txt`. Bila
masih ada `{{?istilah?}}`, putuskan istilahnya:

1. Ganti penanda dengan istilah yang benar, atau
2. tambahkan entri ke `istilah.tsv` di samping `document.md`, lalu build ulang.

Kegagalan verifikasi istilah berarti ada pelanggaran style, misalnya istilah
`italic: yes` ditulis tegak atau run `IstilahAsing` tidak memakai `en-US`.
Italic yang berasal dari style paragraf atau style caption bukan pelanggaran.
Perbaiki naskah atau glosarium, bukan DOCX.

## Bantuan lanjutan

- Periksa pesan `[ERROR]` lengkap; pesan menyebut path dan kode.
- Gunakan `--keep-intermediate` untuk mempertahankan `.laporan-build/` dan
  intermediate DOCX.
- Baca [document-format.md](document-format.md) untuk aturan sumber.
- Baca [docs/dev/pipeline/stages.md](../dev/pipeline/stages.md) untuk urutan stage.

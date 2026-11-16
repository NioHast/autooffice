# Quickstart

Panduan singkat dari naskah kosong sampai DOCX, lalu dari `deck.yaml` sampai
PPTX/Slides. PDF diekspor manual dari Word atau PowerPoint setelah review.
Semua perintah `autooffice` dijalankan dari akar repo:

```bash
uv run autooffice <perintah> ...
```

## Daftar isi

- [1. Pilih struktur](#1-pilih-struktur)
- [2. Siapkan berkas](#2-siapkan-berkas)
- [3. Tulis front matter](#3-tulis-front-matter)
- [4. Check](#4-check)
- [5. Build](#5-build)
- [6. Periksa output](#6-periksa-output)
- [7. Quickstart deck](#7-quickstart-deck)
- [Contoh](#contoh)

## 1. Pilih struktur

Struktur menentukan urutan bab, penomoran, flag TOC, dan daftar. Format
`undip-msi` menentukan margin, font, caption, sitasi, dan aset visual. Isi
front matter (sampul dan halaman pendahulu) ditulis di `document.md`.

| Struktur | Cocok untuk | Bab body | Penomoran |
| --- | --- | ---: | --- |
| `assignment` | Tugas kuliah | 3 | `1.`, `1.1`, `1.1.1` |
| `proposal` | Proposal tesis | 4 | `1.`, `1.1`, `1.1.1` |
| `thesis` | Tesis atau skripsi | 5 | `BAB I`, `1.1`, `1.1.1` |

Contoh `thesis` memuat halaman pengesahan, pernyataan, kata pengantar, abstrak
Indonesia dan Inggris, daftar isi, daftar tabel, daftar gambar, dan lampiran.
Contoh `proposal` memuat halaman persetujuan dan daftar isi. Contoh
`assignment` hanya memuat sampul. Bagian-bagian itu adalah Markdown biasa di
`document.md`, bukan hasil render template.

## 2. Siapkan berkas

Buat direktori kerja dengan isi minimal:

```text
tugas/
|-- document.md
|-- references.bib
`-- gambar/          # opsional, dipakai bila ada gambar
```

Cara tercepat adalah menyalin salah satu contoh dari akar repo, lalu
menyesuaikan isinya:

```bash
cp -r examples/assignment-single tugas
rm -rf tugas/out tugas/.laporan tugas/Tugas.pdf
```

Jangan menyalin `out/` atau `.laporan/` dari contoh. Keduanya artefak build.

## 3. Tulis front matter

Blok YAML wajib berada di awal `document.md` dan dibatasi `---`. Kunci wajib
adalah `title`, `author`, `report_name`, `structure`, dan `format`. Setelah
blok YAML, tulis sampul sebagai Markdown lalu akhiri dengan marker
`<!-- section-break -->`.

````markdown
---
title: "Analisis Pipeline Markdown untuk Laporan Tugas"
author: "Nama Mahasiswa"
nim: "30000000000000"
report_name: "Tugas"
structure: assignment
format: undip-msi
bibliography: references.bib
---

::: {custom-style="CoverTitle"}
ANALISIS PIPELINE MARKDOWN UNTUK LAPORAN TUGAS
:::

::: {custom-style="CoverCourse"}
**Penulisan Laporan Akademik**
:::

\

::: {custom-style="CoverImage"}
![](logo.jpg){width=4.7cm}
:::

\

::: {custom-style="CoverLine"}
Disusun oleh:
:::

::: {custom-style="CoverName"}
**Nama Mahasiswa**
:::

::: {custom-style="CoverLine"}
30000000000000
:::

\

::: {custom-style="CoverInstitution"}
PROGRAM STUDI MAGISTER SISTEM INFORMASI
:::

::: {custom-style="CoverInstitution"}
UNIVERSITAS DIPONEGORO
:::

::: {custom-style="CoverInstitution"}
2026
:::

<!-- section-break -->

# Pendahuluan

Latar belakang dengan sitasi [@pandoc2024].

# Pembahasan

Isi pembahasan.

# Penutup

Kesimpulan.
````

Heading 1 harus sama dengan urutan `body` struktur. Jangan menulis nomor bab.
Rincian kunci dan bentuk front matter ada di
[document-format.md](document-format.md).

## 4. Check

Jalankan pemeriksaan sumber sebelum build:

```bash
uv run autooffice check document.md
```

`check` memvalidasi blok YAML metadata, keberadaan format dan struktur,
bibliografi, gambar body, urutan Heading 1, dan caption Markdown body. Perintah
ini tidak memanggil Pandoc atau Word dan tidak menulis berkas.

Aturan prosa ada di [writing-rules.md](writing-rules.md). Paket AutoOffice tidak
menyertakan pemeriksa prosa terpisah; jalankan `autooffice doctor` untuk
memeriksa perkakas build:

```bash
uv run autooffice doctor
```

Untuk diagram, pasang Java 21 dan PlantUML 1.2026.10, lalu set
`AUTOOFFICE_PLANTUML`. Rinciannya ada di [plantuml.md](plantuml.md).

## 5. Build

Bangun DOCX:

```bash
uv run autooffice build document.md --target docx
```

DOCX memakai field native Word. AutoOffice tidak mengisi hasil field. Sebelum
review atau ekspor PDF, buka DOCX di Word, tekan Ctrl+A lalu F9. Untuk daftar
isi, pengguna juga dapat memakai References > Update Table.

Tambahkan `--keep-intermediate` bila workspace `.laporan-build/` perlu
diperiksa setelah build. Tambahkan `--terms` bila ingin mengaktifkan gate
glosarium. Diagram ditulis sebagai fence `{.plantuml caption="..."}` dan
dirender menjadi PNG saat build.

## 6. Periksa output

Output ditulis di direktori yang sama dengan `document.md`:

```text
tugas/
|-- document.md
|-- references.bib
|-- Tugas.docx
|-- .laporan/
|   `-- manifest.json
`-- .laporan-build/      # hanya dengan --keep-intermediate
```

Nama berkas mengikuti `report_name` yang wajib di front matter. Tidak ada nama
default. Manifest berisi bookmark `pNNNN` untuk penelusuran edit Word.

PDF tidak ditulis oleh build. Setelah DOCX direview dan field diperbarui,
ekspor PDF manual dari Word; lihat [pdf-export.md](pdf-export.md).

## 7. Quickstart deck

Deck memakai satu `deck.yaml` sebagai sumber. Salin contoh demo, lalu hapus
artefak build yang terbawa:

```bash
cp -r examples/demo-deck deck-saya
rm -rf deck-saya/out deck-saya/.autooffice deck-saya/.autooffice-build
```

Edit `deck.yaml`, lalu sesuaikan `copy.yaml`, `transcripts.md`, `assets/`, dan
`diagrams/` bila ada. Path aset relatif terhadap `deck.yaml`.

Periksa sumber tanpa menulis output:

```bash
uv run autooffice check deck-saya/deck.yaml
```

`check` berjalan di Linux, macOS, dan Windows. Build `pptx` juga berjalan di
semua platform tanpa Office, COM, atau `pywin32`. PPTX memakai Arial tanpa
embedding font; layout diukur dengan Liberation Sans yang metrik-kompatibel
Arial.

Bangun PPTX:

```bash
uv run autooffice build deck-saya/deck.yaml --target pptx
```

Sinkronkan ke Google Slides setelah `uv sync --extra google` dan kredensial
OAuth siap. Tutorial OAuth ada di [google-oauth.md](google-oauth.md):

```bash
uv run autooffice build deck-saya/deck.yaml --target slides
```

PDF diekspor manual dari PowerPoint setelah PPTX direview; lihat
[pdf-export.md](pdf-export.md). Di Android, Linux, atau lingkungan tanpa
Arial, aplikasi dapat mengganti Arial dengan Liberation Sans atau font
substitusi lain, sehingga bentuk glyph dapat berbeda.

Rincian authoring ada di [deck-authoring.md](deck-authoring.md), target dan
flag di [CLI AutoOffice](cli.md), dan konsep pipeline di
[deck-pipeline.md](../learn/deck-pipeline.md).

## Contoh

- [assignment-single](../../examples/assignment-single/document.md): tiga bab,
  satu tabel, satu diagram PlantUML.
- [proposal-single](../../examples/proposal-single/document.md): empat bab,
  satu tabel, daftar isi.
- [thesis-single](../../examples/thesis-single/document.md): lima bab, front
  matter lengkap, gambar, PlantUML, persamaan, kode, dan lampiran.

Lanjutkan ke [writing-rules.md](writing-rules.md) sebelum menulis naskah
panjang. Bila ada kegagalan, lihat [troubleshooting.md](troubleshooting.md).

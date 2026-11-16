# 03 - Tahap Pipeline

Halaman ini membahas urutan kerja `Pipeline.run` dan 16 stage kanonik. Setelah
membacanya, pembaca bisa melacak tempat suatu perubahan terjadi, membaca
`StageResult`, dan menelusuri kegagalan stage tanpa menebak.

## Tujuan halaman

Setelah halaman ini, pembaca bisa:

1. menyebutkan 16 stage dan urutannya;
2. membedakan stage yang memutasi workspace, package, dan part DOCX;
3. menjelaskan tahap sebelum save dan save tunggal;
4. membaca `StageResult` dan artifact yang dihasilkan;
5. memilih tes atau perintah untuk mendiagnosis stage yang gagal.

## Prasyarat

- [01 - Model Mental](01-mental-model.md).
- [02 - Build Pertama](02-first-build.md).
- Bisa membaca Python sederhana dan decorator/class dasar.
- Tidak perlu Word. Build DOCX berjalan tanpa Office.

## Daftar isi

- [Kontrak Pipeline.run](#kontrak-pipelinerun)
- [Tiga tahap eksekusi](#tiga-tahap-eksekusi)
- [Enam belas stage kanonik](#enam-belas-stage-kanonik)
- [Guard dan alasan urutan](#guard-dan-alasan-urutan)
- [Satu load dan satu save](#satu-load-dan-satu-save)
- [StageResult dan stage yang dilewati](#stageresult-dan-stage-yang-dilewati)
- [ArtifactStore dan workspace](#artifactstore-dan-workspace)
- [Membaca kegagalan stage](#membaca-kegagalan-stage)
- [Contoh konkret: thesis](#contoh-konkret-thesis)
- [Latihan](#latihan)
- [Halaman berikutnya](#halaman-berikutnya)
- [Referensi dan kontrak](#referensi-dan-kontrak)

## Kontrak Pipeline.run

`Pipeline.run(document_path, options)` melakukan:

1. `load_project(document_path)` untuk membaca front matter, format,
   struktur, dan aset;
2. `_resolve_target(options)` untuk memutuskan target efektif;
3. membuat `output_dir` dengan `autooffice.docx.paths.output_directory`;
4. membuat `Workspace` di `.laporan-build/` di samping dokumen;
5. menjalankan seluruh stage pada satu `DocumentPackage`;
6. menyimpan package satu kali;
7. menulis manifest;
8. membersihkan workspace di blok `finally`, kecuali `--keep-intermediate`.

Tidak ada pass Word, COM, atau PDF setelah save. Kontrak lengkap ada di
[contracts/docx.md](../../contracts/docx.md).

## Tiga tahap eksekusi

| Tahap | Stage | State utama |
| --- | --- | --- |
| Persiapan | `validate` sampai `pandoc` | Workspace, Markdown final, package DOCX baru. |
| Mutasi package | `sections` sampai `lists` | `ctx.package` di memori. |
| Save | `Pipeline` | DOCX final dan manifest di disk. |

`pandoc` adalah satu-satunya stage yang membuat `ctx.package`. Sebelum
`pandoc`, `ctx.package is None`. Setelah `pandoc`, stage lain hanya memutasi
package yang sama.

## Enam belas stage kanonik

| Order | Stage | Modul | Memutasi | Tugas utama |
| ---: | --- | --- | --- | --- |
| 10 | `validate` | `stages/validate.py` | - | Caption tabel dan alt text gambar di Markdown. |
| 20 | `plantuml` | `stages/plantuml.py` | workspace | Render blok PlantUML menjadi PNG dan tulis `plantuml.md`. |
| 30 | `style_reference` | `stages/style_reference.py` | workspace, cache | Hasilkan `reference.docx` turunan dari `format.yaml`. |
| 35 | `front_matter` | `stages/front_matter.py` | workspace | Ganti `<!-- section-break -->` dengan raw `w:sectPr`, penomoran heading, Markdown final. |
| 40 | `pandoc` | `stages/pandoc.py` | package | Markdown final menjadi DOCX awal. |
| 50 | `sections` | `stages/sections.py` | `word/document.xml` | Section break, margin, ukuran halaman, override `numId=0`, verifikasi numbering. |
| 60 | `code` | `stages/code.py` | `word/document.xml` | Blok kode menjadi tabel 1x1. |
| 70 | `captions` | `stages/captions.py` | `word/document.xml` | Caption tabel/gambar, nomor bab, layout gambar. |
| 80 | `normalize` | `stages/normalize.py` | `word/document.xml` | Spasi 1,5, justify, hapus bold body. |
| 90 | `equations` | `stages/equations.py` | `word/document.xml` | Nomor persamaan `(bab.n)`. |
| 100 | `numbering` | `stages/numbering.py` | `word/document.xml`, `word/numbering.xml` | Indentasi daftar. |
| 110 | `blank_lines` | `stages/blank_lines.py` | `word/document.xml` | Paragraf kosong sesuai aturan layout. |
| 120 | `terms` | `stages/terms.py` | `word/document.xml`, `word/styles.xml` | Style istilah, verifikasi, review file. |
| 130 | `toc` | `stages/toc.py` | `word/document.xml` | Field TOC native; style TOC diverifikasi dari reference. |
| 140 | `page_numbers` | `stages/page_numbers.py` | document, header/footer, rels, content types | Romawi front matter, Arab body. |
| 150 | `lists` | `stages/lists.py` | `word/document.xml` | Daftar tabel/gambar dan field `SEQ`. |

Beberapa stage tidak selalu berjalan:

- `terms` hanya aktif dengan `--terms`;
- `toc` dilewati jika `structure.toc` bernilai `false`;
- `lists` dilewati jika `structure.lists.tables` dan `structure.lists.figures`
  bernilai `false`.

Stage `plantuml` menemukan engine lewat `AUTOOFFICE_PLANTUML` (jar atau
executable) dan memakai `AUTOOFFICE_JAVA` bila diberikan. Render memakai
PlantUML 1.2026.10 atau lebih baru di Java 21 dengan `-pipe` (stdin/stdout),
`-secure`, `--pragma layout=smetana`, dpi 192, `--disable-metadata`,
`--threads 1`, `--stop-on-error`, dan `--no-error-image`. PNG ditulis ke
`gambar/plantuml-<hash>.png`; tidak ada kebutuhan Node.js, Chromium, atau
Graphviz.

## Guard dan alasan urutan

Urutan bukan saran. `validate_stage_order` menolak stage yang hilang,
duplikat, salah urutan, atau memutasi part yang tidak dikenal.

Guard penting:

1. `style_reference` sebelum `front_matter` sebelum `pandoc`;
2. `sections` sebelum `code` sebelum `captions` sebelum `normalize`;
3. `normalize` sebelum `equations` sebelum `blank_lines`;
4. `terms` sebelum `toc` sebelum `page_numbers` sebelum `lists`.

Alasannya:

- Reference dan Markdown front matter harus siap sebelum Pandoc membaca
  Markdown.
- Section dan nomor bab harus stabil sebelum caption dan tabel kode diolah.
- Tabel kode harus berbentuk tabel 1x1 sebelum captions agar tidak dianggap
  tabel data.
- Italic istilah memengaruhi paginasi, jadi `terms` harus selesai sebelum TOC
  dan nomor halaman.
- TOC dan `PAGEREF` harus ada sebelum format nomor halaman.

Field TOC dan nomor halaman ditulis sebagai instruksi native. Hasil field
tidak dihitung oleh pipeline. Pengguna membuka DOCX di Word, menekan Ctrl+A
lalu F9, sebelum review atau ekspor PDF.

## Satu load dan satu save

Di `pipeline.py`, seluruh stage berjalan sebelum save:

```python
ctx.package.save(docx_path)
ctx.artifacts.put("docx", docx_path)
```

Setelah save, pipeline selesai. Stage tidak boleh memanggil `load` atau `save`
untuk package target. Pengecualian tunggal adalah `style_reference`, yang
memuat dan menyimpan `reference.docx` sumber, bukan package target.

## StageResult dan stage yang dilewati

Setiap stage mengembalikan `StageResult`:

| Field | Arti |
| --- | --- |
| `stage` | Nama stage, misalnya `captions`. |
| `status` | `ok` atau `skipped`. |
| `changed` | Apakah stage benar-benar mengubah inputnya. |
| `duration_ms` | Durasi dalam milidetik. |
| `metrics` | Angka ringkas, misalnya jumlah field atau byte. |
| `warnings` | Peringatan yang tidak menggagalkan build. |
| `artifacts` | Path yang dihasilkan stage. |

`status="skipped"` bukan error. Contohnya `terms` tanpa `--terms`, `toc` pada
struktur tanpa TOC, dan `lists` tanpa daftar. Warnings dari stage dikumpulkan
di `BuildReport` lalu dicetak CLI.

Error tidak dikembalikan sebagai `StageResult`. Error dilempar sebagai
`DocgenError` atau subclass. Exception yang tidak dikenal dibungkus
`StageError` dengan nama stage, path, dan cause.

## ArtifactStore dan workspace

`ArtifactStore` menyimpan path dengan key yang ketat. Key standar:

| Key | Isi |
| --- | --- |
| `markdown` | Markdown final untuk Pandoc dari `front_matter`. |
| `plantuml.markdown` | Markdown mentah hasil render PlantUML. |
| `reference_docx` | `reference.docx` turunan. |
| `pandoc_docx` | DOCX sementara hasil Pandoc. |
| `docx` | DOCX final di path output. |
| `manifest` | Manifest Adeu. |
| `terms_review` | Review istilah. |

Key berprefix nama stage juga sah. Key yang sudah ada tidak boleh ditimpa
tanpa deklarasi.

Workspace default adalah `.laporan-build/` di samping `document.md`. Tanpa
`--keep-intermediate`, workspace dihapus di blok `finally`, termasuk saat build
gagal. Dengan `--keep-intermediate`, isinya dipertahankan untuk diperiksa,
misalnya `front_matter.md`, `plantuml.md`, `reference.docx`,
`pandoc-metadata.yaml`, dan DOCX antara.

## Membaca kegagalan stage

Format error CLI:

```text
[ERROR] <path>: kunci '<key>': <pesan> (<KODE>)
```

Untuk `StageError`, nama stage muncul di depan:

```text
[ERROR] [captions] <path>: <pesan> (<KODE>)
```

Langkah diagnosis:

1. baca nama stage dan kode error;
2. cari modul stage di tabel 16 stage;
3. baca deklarasi `mutates` dan guard-nya;
4. jalankan tes stage terkait di `tests/docx`;
5. jika perlu, build ulang dengan `--keep-intermediate` dan periksa workspace.

Jangan mengubah urutan stage atau menambahkan fallback sebelum penyebab
ditemukan. `validate_stage_order` sengaja keras agar kesalahan urutan tidak
menghasilkan output yang tampak benar.

## Contoh konkret: thesis

`examples/thesis-single/document.md` memakai struktur `thesis`. Struktur itu
memiliki TOC dan daftar tabel/gambar. Tanpa `--terms`, alur efektifnya:

```text
validate
-> plantuml
-> style_reference
-> front_matter
-> pandoc
-> sections
-> code
-> captions
-> normalize
-> equations
-> numbering
-> blank_lines
-> terms (skipped)
-> toc
-> page_numbers
-> lists
-> save
```

Dengan `--terms`, stage `terms` berjalan dan menulis review file. Tidak ada
stage Word atau PDF setelah save. Field DOCX diperbarui manual di Word.

## Latihan

### 1. Cetak urutan kanonik

Jalankan:

```bash
uv run python -c "from autooffice.docx.pipeline import CANONICAL_ORDER; print(len(CANONICAL_ORDER)); print(', '.join(item.value for item in CANONICAL_ORDER))"
```

Cara memeriksa: angka pertama harus `16`, lalu daftar dimulai `validate` dan
diakhiri `lists`. Jika ada stage tambahan atau hilang, kontrak pipeline
berubah.

### 2. Temukan stage yang memutasi part tertentu

Jalankan:

```bash
rg -n "mutates = frozenset" src/autooffice/docx/stages
```

Cocokkan hasilnya dengan tabel stage. Stage yang tidak dideklarasikan sebagai
pemutasi part tidak boleh menulis `word/document.xml`.

## Halaman berikutnya

Lanjut ke [04 - Model DOCX](04-docx-model.md) untuk memahami package yang
dimutasi stage.

## Referensi dan kontrak

| Kebutuhan | Dokumen |
| --- | --- |
| Kontrak DOCX | [contracts/docx.md](../../contracts/docx.md) |
| Model eksekusi | [pipeline/overview.md](../pipeline/overview.md) |
| Urutan stage | [pipeline/stages.md](../pipeline/stages.md) |
| Opsi build | [pipeline/options.md](../pipeline/options.md) |
| Ekspor PDF manual | [pdf-export.md](../../user/pdf-export.md) |

### Referensi resmi

Label registry yang dipakai halaman ini: `Python 3.15 language reference`,
`Pandoc manual`, `OOXML ECMA-376`, dan `PlantUML command line`. URL resminya
ada di [registry referensi](../references.md).

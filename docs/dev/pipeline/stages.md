# Urutan Stage

Halaman ini memuat urutan kanonik stage dan guard yang wajib ditegakkan.
Kontrak stage ada di [contracts/docx.md](../../contracts/docx.md).

## Urutan stage

| Order | Stage | Modul | Memutasi | Catatan |
| ---: | --- | --- | --- | --- |
| 10 | `validate` | `autooffice/docx/stages/validate.py` | - | Caption tabel dan alt text gambar. |
| 20 | `plantuml` | `autooffice/docx/stages/plantuml.py` | workspace | Blok PlantUML menjadi PNG. |
| 30 | `style_reference` | `autooffice/docx/stages/style_reference.py` | workspace, cache | `reference.docx` turunan dari `format.yaml`. |
| 35 | `front_matter` | `autooffice/docx/stages/front_matter.py` | workspace | Sampul, template, abstrak, finalisasi heading Markdown (uppercase + `w:br`); nomor heading ditulis Word dari `numbering.xml`. |
| 40 | `pandoc` | `autooffice/docx/stages/pandoc.py` | package | Markdown menjadi DOCX. |
| 50 | `sections` | `autooffice/docx/stages/sections.py` | `word/document.xml` | Section break, margin, ukuran halaman, nomor heading DOCX. |
| 60 | `code` | `autooffice/docx/stages/code.py` | `word/document.xml` | Blok kode menjadi tabel 1x1. |
| 70 | `captions` | `autooffice/docx/stages/captions.py` | `word/document.xml` | Caption wajib, nomor bab, layout gambar. |
| 80 | `normalize` | `autooffice/docx/stages/normalize.py` | `word/document.xml` | Spasi 1,5, justify, hapus bold body. |
| 90 | `equations` | `autooffice/docx/stages/equations.py` | `word/document.xml` | Nomor persamaan `(bab.n)`. |
| 100 | `numbering` | `autooffice/docx/stages/numbering.py` | `word/document.xml`, `word/numbering.xml` | Indentasi daftar. |
| 110 | `blank_lines` | `autooffice/docx/stages/blank_lines.py` | `word/document.xml` | Paragraf kosong sesuai aturan layout. |
| 120 | `terms` | `autooffice/docx/stages/terms.py` | `word/document.xml`, `word/styles.xml` | Hanya aktif dengan `--terms`. |
| 130 | `toc` | `autooffice/docx/stages/toc.py` | `word/document.xml`, `word/styles.xml` | Field TOC native bila `structure.toc`. |
| 140 | `page_numbers` | `autooffice/docx/stages/page_numbers.py` | document, header/footer, rels, content types | Romawi front matter, Arab body. |
| 150 | `lists` | `autooffice/docx/stages/lists.py` | `word/document.xml` | Daftar tabel/gambar dan field `SEQ`. |

Stage `plantuml` membaca fence `{.plantuml caption="..."}` dengan caption
wajib dan isi tidak kosong, menulis PNG ke `gambar/plantuml-<hash>.png`, dan
menulis Markdown hasil penggantian ke `plantuml.md` dengan artefak
`plantuml.markdown`. Engine diambil dari `AUTOOFFICE_PLANTUML` (jar atau
executable); `AUTOOFFICE_JAVA` opsional. Hasil render disimpan juga di cache
persisten `.laporan/cache/plantuml`, sehingga build berikutnya memakai ulang PNG
yang sama tanpa memanggil PlantUML walau workspace sudah dibersihkan.

Render memakai PlantUML 1.2026.10 atau lebih baru di Java 21 dengan `-pipe`,
`-secure`, `--pragma layout=smetana`, dpi 192, `--disable-metadata`,
`--threads 1`, `--stop-on-error`, dan `--no-error-image`. Tidak ada kebutuhan
Node.js, Chromium, atau Graphviz. Rincian ada di
[kontrak PlantUML](../../contracts/plantuml.md).

## Guard

- `style_reference` sebelum `front_matter`;
- `front_matter` sebelum `pandoc`;
- `sections` sebelum `code`, lalu `captions`, `normalize`, `equations`;
- `terms` sebelum `toc`, `toc` sebelum `page_numbers`, `page_numbers` sebelum
  `lists`.

Stage yang salah urutan, duplikat, atau memutasi part tidak dikenal
menggagalkan `validate_stage_order`.

Stage `toc`, `page_numbers`, dan `lists` menulis field native, tetapi tidak
mengisi hasil field. Field diisi pengguna di Word dengan Ctrl+A lalu F9.
Tidak ada stage `office` atau `pdf`; AutoOffice tidak memakai COM.

## Batas stage

Stage tidak boleh memanggil `load` atau `save` package target. Model satu load
dan satu save dijelaskan di [overview.md](overview.md#satu-load-dan-satu-save).
Opsi yang mengaktifkan stage tertentu ada di [options.md](options.md).

## Referensi resmi

Label registry yang dipakai halaman ini: `Pandoc manual`, `PlantUML command
line`, dan `PlantUML security`. URL resminya ada di
[registry referensi](../references.md).

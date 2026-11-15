# Arsitektur

AutoOffice memisahkan naskah, aturan tampilan, urutan struktur, dan orkestrasi
menjadi dua pipeline: DOCX dari Markdown dan PPTX/Slides dari YAML. Satu
`document.md` atau satu `deck.yaml` adalah sumber konten. Format, struktur,
layout, dan theme adalah data paket yang dibaca saat runtime.

## Lapisan

| Lapisan | Lokasi | Tanggung jawab | Tidak boleh berisi |
| --- | --- | --- | --- |
| Konten DOCX | `document.md`, `references.bib`, `istilah.tsv`, `gambar/` | Teks, sitasi, glosarium tambahan, dan aset | Aturan margin, urutan bab, field Word |
| Struktur DOCX | `src/autooffice/docx/data/structures/<id>/structure.yaml` | Urutan front matter, body, back matter, penomoran, TOC, daftar, cover | Nilai margin, font, CSL |
| Format DOCX | `src/autooffice/docx/data/formats/<id>/format.yaml` | Halaman, font, heading, caption, kode, sitasi, aset visual | Teks naskah, urutan bab |
| Pipeline DOCX | `src/autooffice/docx/` | Validasi, orkestrasi stage, mutasi DOCX, output, manifest | Teks naskah, salinan aturan format |
| Konten deck | `deck.yaml`, `transcripts.md`, `assets/`, `diagrams/` | Meta, slide, block, aset, transkrip | Token warna, layout preset, kode renderer |
| Pipeline deck | `src/autooffice/deck/`, `src/autooffice/design/` | Compiler DeckIR, layout, copy checker, renderer, chart, media PlantUML, transkrip | Teks naskah DOCX, aturan format Word |
| Permukaan CLI | `src/autooffice/cli/` | Target, output, check, doctor, orkestrasi domain | Logika XML atau renderer |

ID format dan struktur adalah nama direktori. Skema keduanya tertutup: kunci
yang tidak dikenal ditolak dengan pesan error.

## Alur DOCX

```text
document.md
  |
  +-- validate             front matter, aset, caption Markdown
  +-- plantuml             blok PlantUML menjadi PNG di workspace
  +-- style_reference      reference.docx turunan dari format.yaml
  +-- front_matter         sampul, template, abstrak, finalisasi heading Markdown
  +-- pandoc               Markdown menjadi DOCX
  |
  +-- package DOCX di memori
  |     +-- sections, code, captions, normalize, equations, numbering
  |     +-- blank_lines, terms, toc, page_numbers, lists
  |     +-- Adeu hook (bookmark pNNNN dan manifest)
  |
  +-- save satu kali
  +-- manifest ditulis
  +-- selesai (field native belum diisi)
```

Pipeline tidak menjalankan Word atau aplikasi Office. Field `TOC`, `PAGEREF`,
`SEQ`, dan `PAGE` ditulis sebagai field native beserta instruksinya, tetapi
hasil field tidak diisi. Pengguna membuka DOCX di Word, menekan Ctrl+A lalu
F9, sebelum review atau ekspor PDF manual.

Urutan stage ditegakkan oleh `autooffice.docx.pipeline`. Stage tidak boleh
memanggil `load` atau `save` package target. Kontrak API ada di
[contracts/docx.md](../contracts/docx.md).

## Alur deck

```text
deck.yaml + transcripts.md
  |
  +-- compile              schema, key, DeckIR, coverage plan
  +-- design               theme, token Arial, kontras
  +-- layout               preset atau custom rows, overflow, grid 12 kolom
  +-- copy checker         aturan prosa dan diagnosis
  +-- media                berkas .puml menjadi PNG PlantUML
  +-- render PPTX          native shape, table, chart, image, notes
  +-- slides               sinkronisasi Google Slides
```

Renderer menulis family `Arial` tanpa embedding font. Layout diukur dengan
Liberation Sans yang metrik-kompatibel Arial. Target `pptx` adalah jalur
offline yang berjalan di semua platform. Target `slides` memerlukan extra
`google` dan kredensial OAuth; mode sync `pull`, `diff`, dan `apply` juga
memerlukan state yang valid. Kontrak renderer dan Google ada di
[contracts/README.md](../contracts/README.md).

## Invariant utama

1. **Satu sumber konten.** Hanya `document.md` atau `deck.yaml` dan asetnya
   yang menjadi sumber. DOCX, PPTX, dan Slides adalah artefak. PDF adalah
   hasil ekspor manual pengguna, bukan artefak build.
2. **Satu load dan satu save DOCX.** `DocumentPackage` dimuat sekali setelah
   Pandoc dan disimpan sekali. Tidak ada pass Word setelah save.
3. **Urutan kanonik.** Stage DOCX berjalan dengan urutan tetap dan guard
   keras. Stage yang salah urutan menggagalkan pipeline.
4. **Part non-target byte-identik.** Stage hanya memutasi part yang
   dideklarasikan. Part lain tidak berubah.
5. **Output di samping input.** Output pengguna ditulis di samping
   `document.md` atau `deck.yaml`; contoh repo memakai `out/`.
6. **Manifest deterministik.** Manifest Adeu tidak memuat timestamp dan
   diurutkan stabil. `text_sha256` dihitung dari teks final.
7. **Data paket mandiri.** `src/autooffice/docx/paths.py` membaca data dari
   paket dan tidak memiliki fallback ke direktori kerja.

## Package DOCX

`src/autooffice/docx/package/` adalah satu-satunya pemilik ZIP dan XML Word:

- `package.py`: model `DocumentPackage`, load, save, part, relationship.
- `io.py`: baca dan tulis ZIP secara atomic.
- `xml.py`: parse, serialisasi, c14n, hash, helper XML.
- `names.py`: konstanta namespace dan style.
- `styles.py`, `sections.py`, `layout.py`, `captions.py`, `tables.py`: format
  dan struktur halaman.
- `heading_numbering.py`, `numbering.py`, `fields.py`, `bookmarks.py`: nomor,
  field Word, dan bookmark.
- `terms/`: glosarium dan transformasi istilah.

Dokumen rinci ada di [docx/README.md](docx/README.md).

## CLI dan entry point

`pyproject.toml` mendaftarkan `autooffice = "autooffice.cli.main:main"`.
Perintah yang tersedia:

```bash
uv run --project <repo> autooffice check <input>
uv run --project <repo> autooffice build <input> --target <targets> [opsi]
uv run --project <repo> autooffice doctor [opsi]
```

Tidak ada perintah `new` atau `list`, dan tidak ada subperintah `reconcile`
pada permukaan AutoOffice v1. Kontrak CLI ada di
[contracts/cli.md](../contracts/cli.md).

## Platform

| Platform | DOCX | PPTX | Slides |
| --- | --- | --- | --- |
| Windows | ya | ya | ya dengan Google OAuth |
| Linux/macOS | ya | ya | ya dengan Google OAuth |
| Android atau viewer tanpa Arial | ya | ya, dengan substitusi font | ya dengan Google OAuth |

Tidak ada dependensi Office, COM, `pywin32`, atau Windows-only. DOCX dan PPTX
dibangun murni dengan Python. Render diagram memakai PlantUML 1.2026.10 atau
lebih baru dari `AUTOOFFICE_PLANTUML` (jar atau executable) dengan Java 21;
`AUTOOFFICE_JAVA` opsional untuk menunjuk executable Java. Tidak ada kebutuhan
Node.js, Chromium, atau Graphviz. Arial umumnya tersedia di Windows dan macOS;
lingkungan tanpa Arial dapat menggantinya dengan Liberation Sans atau font
substitusi lain. Tata letak tetap dihitung dengan metrik Liberation Sans yang
kompatibel Arial. Alur ekspor PDF manual ada di
[pdf-export.md](../user/pdf-export.md).

## Batasan arsitektur

- Tidak ada mode folder atau file bab terpisah untuk DOCX.
- Tidak ada filter Lua. Perilaku lama diport ke stage Python.
- Tidak ada mesin PDF, adapter COM, atau dependensi Windows-only.
- Build memakai pipeline Python; tidak ada jalur shell atau fallback lama.
- TOC dan daftar DOCX memakai field native yang tidak diisi otomatis. Pengguna
  memperbarui field di Word dengan Ctrl+A lalu F9.

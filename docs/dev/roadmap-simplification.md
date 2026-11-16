# Roadmap Penyederhanaan DOCX

- Status: rencana, belum dikerjakan
- Tanggal: 2026-11-16
- Rujukan: [ADR 0018](../decisions/0018-retire-styles-and-disable-highlighting.md),
  [ADR 0015](../decisions/0015-native-heading-numbering.md),
  [format dan struktur](formats.md), dan [style DOCX](docx/styles.md)

## Konteks

Rilis 4.0.0 sudah menghapus dua sumber drift yang jelas: style yang tidak
pernah dipakai dan syntax highlighting yang tidak pernah sampai ke output.
Sisa kompleksitas ada di jalur yang masih membangkitkan style, geometri
halaman, front matter, dan transformasi DOCX dari Python.

Roadmap ini mencatat urutan pengurangan itu secara bertahap. Setiap fase
adalah kontrak tersendiri: tidak ada fase yang boleh mencampur perubahan
schema, stage, dan output tanpa ADR. Semua perkiraan LOC adalah pengurangan
kode Python yang terlibat, bukan target ukuran seluruh repo.

## Fase

| Fase | Isi | Prasyarat | Perkiraan |
| --- | --- | --- | --- |
| 2a | Bake style ke reference (sedang berjalan di branch lain). | — | -630 LOC |
| 2a-b | Hapus mode penomoran caption `document`; hanya `chapter`. | 2a | -60…-80 LOC |
| 2b | Header/footer/margin dari reference; `page_numbers` menyusut; **memperbaiki bug footer Romawi front matter**. | 2a | -228 LOC |
| 3a | Konvensi nama file (`references.bib`, `citation.csl`, `logo.jpg`). | 2b | -150 LOC |
| 3b | Front matter pindah ke `document.md`; cover memakai `\` sebagai pengganti `spacer()`. | 2b | -607 LOC |
| 3c | `format.yaml` dibubarkan tanpa sisa; tidak perlu key `figure_numbering` di front matter. | 3b | -1.400 LOC |
| 4 | `terms`, `blank_lines`, `equations` menjadi filter JSON. | 3c | -1.019 LOC |

Jumlah indikatif seluruh fase: sekitar **4.094–4.114 LOC**. Angka per fase
adalah perkiraan dan tidak boleh dipakai sebagai janji rilis.

## Rincian fase

### 2a — Bake style ke reference

Seluruh style yang saat ini dibangkitkan `style_reference.py` dipindahkan ke
`reference.docx` sumber. Build tidak lagi menulis ulang `word/styles.xml` dari
`format.yaml`; stage dan spec style runtime menyusut. Fase ini sedang berjalan
di branch lain dan belum menjadi bagian dari rilis ini.

### 2a-b — Hapus mode penomoran caption `document`

`figures.numbering` saat ini menerima dua nilai: `chapter` (`Gambar 2.3`) dan
`document` (`Gambar 7`). Pengguna memutuskan hanya mode `chapter` yang
dibutuhkan.

Yang dihapus:

- field `CaptionSpec.numbering`;
- parameter `scope` pada `format_captions`/`renumber_captions`/
  `_number_caption`/`_heading_chapter` (`package/captions.py`,
  `stages/captions.py`, dan `stages/lists.py`);
- key `figures.numbering` di `format.yaml` beserta parsing dan validasinya di
  `config/format.py`;
- percabangan `if scope == "chapter"`, termasuk `\s 1` di `stages/lists.py`
  yang kini selalu dipakai;
- dua test yang memakai mode `document` di `tests/docx/test_lists.py` dan
  `tests/docx/test_stages_captions.py`.

Perkiraan: **-60 sampai -80 LOC**.

**Efek penting.** Setelah fase ini tidak ada lagi flag perilaku di
`format.yaml`. Bersama `code.highlight` yang sudah dihapus di 4.0.0, fase 3c
dapat membubarkan `format.yaml` tanpa sisa; tidak perlu key `figure_numbering`
di front matter.

**Prasyarat:** 2a selesai, karena keduanya menyentuh `stages/lists.py`.

**Acceptance:** output tesis identik (21 halaman, heading+caption 36/36,
sha256 dua build sama); caption sebelum bab pertama tetap dilewati tanpa
nomor, sehingga perilaku `chapter` tidak berubah.

### 2b — Header, footer, dan margin dari reference

Geometri halaman, margin, header, footer, dan field nomor halaman dipindahkan
ke reference dan section default. `page_numbers` hanya menyisakan bagian yang
benar-benar dinamis. Fase ini juga memperbaiki bug footer Romawi front matter
yang tercatat di ADR 0015: semua section front matter mereferensikan
`footer1.xml`, lalu stage `page_numbers` menimpa part itu sebagai footer body
yang tersembunyi.

### 3a — Konvensi nama file

`references.bib`, `citation.csl`, dan `logo.jpg` dicari berdasarkan konvensi
di direktori format, bukan melalui key `citation.bibliography`, `citation.csl`,
dan `assets.logo`. Key konfigurasi yang menjadi redundan dihapus.

### 3b — Front matter di `document.md`

Front matter yang sekarang dibangkitkan Python ditulis di `document.md`.
Sampul memakai baris `\` untuk jarak vertikal sebagai pengganti `spacer()`.
`front_matter.py`, placeholder template, dan raw OpenXML untuk jarak ikut
menyusut.

### 3c — `figure_numbering` dan pembubaran `format.yaml`

`figure_numbering` menjadi baris front matter, bukan key `figures.numbering`
di `format.yaml`. Sisa `format.yaml` dibagikan ke reference dan front matter
sampai file itu tidak lagi diperlukan. Parser format, model konfigurasi, dan
validasi key ikut menyusut.

### 4 — `terms`, `blank_lines`, dan `equations` sebagai filter JSON

Tiga stage Python diganti filter yang bekerja pada AST JSON Pandoc. Walker
OOXML khusus untuk ketiga transformasi itu dihapus; pipeline hanya menjalankan
filter pada urutan yang sama.

## Yang tetap di Python

Penyederhanaan ini tidak menghapus Python sepenuhnya. Empat area berikut tetap
di Python karena filter dan `reference.docx` tidak dapat menggantikannya:

- **`package/` (9.505 LOC).** `DocumentPackage`, part, relationship, style,
  numbering, section, field, bookmark, dan tabel adalah operasi tingkat paket
  DOCX. Filter hanya melihat AST Markdown; `reference.docx` hanya menyediakan
  definisi style. Keduanya tidak dapat membuat atau memperbarui part seperti
  `word/numbering.xml`, `word/header*.xml`, `word/footnotes.xml`, atau
  `.laporan/manifest.json`.
- **Pipeline.** Urutan stage, satu `load`/`save`, workspace, artefak antara,
  kode error, validasi input, dan CLI tetap milik orkestrator. Filter tidak
  memiliki siklus hidup package.
- **PlantUML.** Render diagram membutuhkan proses Java 21, cache, hash,
  sidecar, mode `-secure`, dan penanganan error eksternal.
- **Adeu.** Bookmark `pNNNN`, manifest, source scan, dan rekonsiliasi bekerja
  pada package DOCX dan tidak dapat dilakukan oleh filter AST.

Batas ini yang membuat target LOC tidak menuju nol: yang dihapus adalah
lapisan konfigurasi dan transformasi yang memang bisa dipindahkan ke reference
atau filter, bukan mesin paket DOCX.

## Gate per fase

Setiap fase harus lulus gate yang sama sebelum dianggap selesai:

- build dokumen uji tetap 21 halaman;
- heading dan caption tetap 36/36 identik setelah field diperbarui;
- dua build berturut-turut menghasilkan sha256 yang sama;
- gate parity style dan kontrak DOCX tetap lulus;
- `uv run python tools/quality/check_docs.py` keluar 0.

## Keputusan terbuka

1. **Tag `v4.0.0`.** Tag sudah ter-push pada `3a21c63`, sedangkan ADR 0018
   ditulis setelah tag. Pilihannya: biarkan tag di commit rilis dan jadikan
   ADR catatan pasca-rilis, atau pindahkan tag ke commit yang memuat ADR
   (perlu force-push tag dan pengumuman ulang). Belum diputuskan.
2. **`spacer()` diganti `\`.** Satu `spacer()` sekarang menulis 640 twip.
   Baris `\` menghasilkan jarak sekitar 720 twip, selisih 80 twip atau
   0,14 cm. Perlu diputuskan apakah selisih itu diterima atau `spacer()`
   dipertahankan untuk jarak yang presisi.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)

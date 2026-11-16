# ADR 0015: Numbering Heading Native Word

- Status: diterima
- Tanggal: 2026-11-15
- Pemilik: DOCX owner
- Rujukan: [ADR 0006](0006-quality-migration-and-humanizer.md),
  [ADR 0013](0013-remove-pdf-arial.md),
  [kontrak DOCX](../contracts/docx.md),
  [numbering DOCX](../dev/docx/numbering.md), dan
  [format.yaml](../dev/formats.md)

## Daftar isi

- [Konteks](#konteks)
- [Keputusan](#keputusan)
- [Konsekuensi](#konsekuensi)
- [Alternatif yang ditolak](#alternatif-yang-ditolak)
- [Bukti](#bukti)
- [Status](#status)
- [Amandemen: STYLEREF dihapus](#amandemen-styleref-dihapus)

## Konteks

Sebelum ADR ini, nomor heading ditulis Python sebagai teks literal di dalam
run: `BAB I`, `1.1`, `1.2.1`. Nomor ditulis dua kali — sekali ke Markdown
sebelum Pandoc oleh `markdown/headings.py`, lalu dibangun ulang di DOCX oleh
`package/heading_numbering.py`. Keduanya memakai counter manual dan
`format_roman`.

Konsekuensinya:

- Word tidak mengenali nomor sebagai list label. `ListFormat.ListString`
  kosong dan `w:numPr` tidak ada pada heading.
- `STYLEREF` di header bergantung pada teks heading, sehingga nomor ikut
  tersalin sebagai teks dan ikut berubah bila judul disunting.
- Tiga modul menyimpulkan nomor bab dengan mem-parse teks heading:
  `package/captions.py`, `stages/equations.py`, dan `package/sections.py`.
  Coupling lain yang ditemukan saat migrasi: `stages/sections.py`
  (section break), `package/fields.py` (posisi TOC), dan numberer Markdown.
- Nomor tidak dapat diperbarui Word saat bab disisipkan atau diurutkan ulang;
  pengguna harus mengubah teks secara manual.

Pengguna memilih perilaku yang paling dekat dengan pemformatan manual Word:
nomor adalah list label native, bukan teks. Pandoc hanya menulis
`<w:pStyle w:val="Heading1"/>` pada paragraf heading, sehingga numbering harus
dinyatakan sekali di reference turunan (`w:numPr` pada style) dan bukan di
setiap paragraf.

## Keputusan

1. **Numbering dipindah ke style dan `word/numbering.xml`.** Reference turunan
   menulis satu `w:abstractNum` dan satu `w:num` berisi level 1-3, lalu
   memasang `w:numPr` pada style `Heading1`, `Heading2`, dan `Heading3`. Id
   dialokasikan dinamis dari rentang bebas `abstractNumId < 990` dan
   `numId < 1000`; id milik list lain tidak pernah ditimpa dan build gagal bila
   tidak ada id bebas. Level 1 memakai `BAB %1`
   (`upperRoman`) untuk `BAB_ROMAN` atau `%1.` (`decimal`) untuk
   `ARABIC_DOTTED`; level 2 `%1.%2.` dan level 3 `%1.%2.%3.` dengan
   `w:isLgl`. Titik akhir mengikuti `sub_dot`/`subsub_dot` dari
   `structure.numbering`.
2. **Heading tak bernomor memakai override paragraf `numId=0`.** Front
   matter, Lampiran, DAFTAR PUSTAKA, H2/H3 di bawah H1 tak bernomor, dan H2/H3
   sebelum H1 bernomor memakai `<w:numPr><w:numId w:val="0"/></w:numPr>`.
   Tidak ada run atau teks heading yang dibangun ulang.
3. **`TOCHeading` memakai `numId=0`.** Judul daftar isi tidak boleh ikut
   mendapat label `BAB`.
4. **Nomor bab caption dan persamaan dihitung dari hitungan H1 bernomor
   berurutan**, bukan parsing teks. Klasifikasi memakai `structure.body`,
   keberadaan `structure.back_matter`, dan `numId=0` (`classify_chapters`) sehingga heading front matter bernama tak
   dikenal dan H1 unnumbered di tengah body tetap dikenali. Caption dan
   persamaan sama-sama menerima `ChapterTitle`. Caption tetap memakai `SEQ` +
   prefix bab literal; nomor persamaan `(bab.n)` tetap literal.
5. **`STYLEREF` memakai dua field**: `STYLEREF "heading 1" \n` untuk nomor dan
   `STYLEREF "heading 1"` untuk judul. Section back matter memakai header
   `PAGE` saja karena `\n` pada heading tak bernomor menghasilkan `0`.
6. **Caption tidak ikut dipindah ke list numbering.** Caption tetap
   `SEQ <label> \* ARABIC \s 1` + teks literal.
7. **Judul H1 `BAB_ROMAN` tetap dua baris.** `finalize_markdown_headings`
   menyisipkan raw inline `w:br` sebelum judul, dan level numbering memakai
   `w:suff="nothing"` sehingga label `BAB N` berada di baris pertama.

## Konsekuensi

- Nomor heading tidak lagi ada di teks `document.xml`. Pencarian
  `grep "BAB I"` pada DOCX tidak lagi menemukan heading; nomor hanya terlihat
  sebagai list label Word.
- `STYLEREF` wajib memakai switch `\n`. Tanpa switch, header hanya memuat
  judul dan kehilangan nomor. Pengukuran Word 16: `\n` menghasilkan
  `BAB I`, sedangkan `\s` hanya `I`.
- Judul TOC dan daftar tabel/gambar tidak ikut bernomor karena style-nya
  memakai `numId=0`; `TOCHeading` juga wajib `numId=0`.
- Output DOCX berubah: heading tanpa teks nomor, `word/numbering.xml` baru
  pada turunan yang belum memilikinya, dan header `STYLEREF`. Golden
  `tests/fixtures/golden/docx/minimal/baseline.json` diregenerasi lewat
  `tests/fixtures/golden/docx/minimal/normalize.py --update`.
- Reference turunan sekarang bergantung pada `structure.numbering`, bukan
  hanya `format.yaml`. Dua struktur dengan `BAB_ROMAN` dan `ARABIC_DOTTED`
  menghasilkan `lvlText` berbeda.
- Id numbering dialokasikan dinamis; base reference yang sudah memakai id
  tertentu tidak ditimpa. Bila seluruh rentang id bebas habis, build gagal
  dengan pesan jelas.
- `.unnumbered`/`{-}` dari Markdown tidak terbawa ke DOCX karena Pandoc
  membuang atributnya; klasifikasi produksi memakai `structure.body` dan
  urutan heading, bukan marker teks.
- Build penuh menjadi byte-identik karena part header/footer baru memakai
  timestamp ZIP tetap (`2020-01-01`), bukan `time.localtime()`.
- **Bug pre-existing ditemukan saat verifikasi, bukan diperbaiki di sini:**
  footer Romawi front matter tidak tampil di Word. Semua section front matter
  mereferensikan `footer1.xml`; stage `page_numbers` kemudian menulis ulang
  part itu sebagai footer body yang hidden (`vanish` + putih). Baseline
  literal dan build native sama-sama tidak menampilkan footer pada halaman
  2-9. Perbaikan memerlukan task terpisah.
- Heading H1 tak bernomor di dalam section body (bukan back matter) akan
  membuat `STYLEREF \n` menghasilkan `0`; kombinasi ini belum ditangani.
  Marker `.unnumbered`/custom style pada heading body arbitrer juga tidak
  terbawa Pandoc karena atribut dibuang; deteksi DOCX mengandalkan nama
  front/back matter dan marker `{-}` literal. Keduanya keterbatasan yang
  diketahui, bukan regresi baru.

## Alternatif yang ditolak

- **Tetap literal.** Alasan lama adalah determinisme, tetapi pengukuran
  menunjukkan dua build byte-identik pada pendekatan native juga. Yang
  berbeda hanya observability: Word tidak mengenali nomor, `STYLEREF`
  bergantung teks, dan nomor tidak dapat diperbarui otomatis.
- **Caption ikut list numbering.** Ditolak karena akan mematikan `TOC \c`,
  bookmark caption, dan cross-reference gambar yang sudah bekerja dengan
  `SEQ` + bookmark.
- **`--number-sections`.** Ditolak karena Pandoc menambahkan teks nomor di
  atas numbering style dan menghasilkan nomor dobel.
- **`w:numPr` di setiap paragraf heading.** Ditolak karena Pandoc hanya
  menulis `<w:pStyle w:val="HeadingN"/>`; menambah `w:numPr` per paragraf
  memerlukan raw OpenXML atau post-processing yang lebih rapuh daripada
  style-level numbering.
- **Memakai id tetap 10.** Ditolak karena dapat menimpa list lain pada
  reference sumber; id dialokasikan dinamis dan diverifikasi.
- **Lua filter atau custom writer.** Ditolak karena filter hanya bisa
  mengubah AST, bukan mengemit paket DOCX; custom writer menghasilkan teks,
  bukan ZIP. Filter raw OpenXML kehilangan bookmark dan melewati mesin
  heading Pandoc.

## Bukti

- Jumlah halaman: **21 → 21** (Word `ComputeStatistics(2)`).
- Perbandingan PDF per halaman: **0/21 halaman berbeda** pada baris body
  (header/footer dikecualikan).
- Heading + caption di Word setelah field diperbarui: **36/36 identik**
  (`ListString` + `Range.Text`), termasuk `BAB I`…`BAB V`, `1.1.`…`5.2.`,
  `Lampiran`, `DAFTAR PUSTAKA`, dan caption `Tabel 2.1`, `Gambar 3.1`,
  `Gambar 4.1`, `Tabel 4.1`.
- Tesis `BAB_ROMAN` dan proposal `ARABIC_DOTTED` sama-sama 21/21 dan 9/9
  halaman; heading+caption 36/36 dan 14/14 identik di Word.
- Header `ARABIC_DOTTED` sebelum perbaikan berimpit (`4JADWAL PENELITIAN 5`
  satu baris); setelah perbaikan menjadi `4` di baris 1 dan `JADWAL
  PENELITIAN` di baris 2, dengan nomor halaman di tab kanan.
- Determinisme: dua build tesis menghasilkan sha256 identik
  `b0340aed017c6931b520dbcbfcf09aaf48805c3c65b7069de2a70389b1204961`;
  proposal `58c66993236abb2d8e5970a5f300fe80e75fc22e0995c47b4f4fa091e5e12b02`.
- Suite: **3529 test lulus**, 2 skipped, 8 deselected; coverage global
  **90.67%** (policy PASS; adapter DOCX 86.26%).
- LOC: enam file legacy **−504 baris**; `package/native_numbering.py` baru
  **+421 baris**; net **−83 baris** pada berkas yang terlibat migrasi di
  `src/`.
- Fungsi dihapus: **13** dari `package/heading_numbering.py` dan **6** dari
  `markdown/headings.py`.
- Detail pengukuran dan gate ada di `tests/docx/test_native_numbering.py`
  dan `tests/docx/test_style_parity.py`.

## Status

Diterima. Perubahan mekanisme numbering heading atau cara caption/persamaan
memperoleh nomor bab memerlukan ADR baru. Bug footer Romawi front matter dan
drift style `TOC1`/`TOC2`/`TOC3`/`TableofFigures` dicatat sebagai pekerjaan
lanjutan, bukan bagian ADR ini.

## Amandemen: STYLEREF dihapus

- Tanggal: 2026-11-16

Fitur header berjalan berbasis `STYLEREF` dicabut karena tidak dibutuhkan
untuk saat ini. Keputusan numbering native Word pada ADR ini **tetap
berlaku**: `w:numPr`, `word/numbering.xml`, dan override `numId=0` tidak
berubah. Konsekuensinya, header body kembali tanpa teks (hanya field `PAGE`),
tanpa salinan nomor atau judul bab. `PageFormat.header_style_ref`, pembangkit
field `STYLEREF`, dan helper `resolve_style_name` dihapus. Pencabutan ini
tidak memakai ADR baru; amandemen ini bagian dari ADR 0015.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)

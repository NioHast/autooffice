# Numbering dan Heading

Halaman ini menjelaskan penomoran heading DOCX dan helper angka Romawi.
Kontrak ada di [contracts/docx.md](../../contracts/docx.md).

Nomor heading **tidak lagi ditulis sebagai teks**. Label `BAB I`, `1.1`,
`1.1.1` dihasilkan Word dari `word/numbering.xml` dan `w:numPr` pada style
`Heading1`..`Heading3`. Pipeline hanya mematikan numbering pada heading yang
tidak boleh bernomor dan mengatur tampilan Markdown.

## Status dan amandemen

Mekanisme ini ditetapkan oleh
[ADR 0015](../../decisions/0015-native-heading-numbering.md) (numbering heading
native Word). Perubahan pada `numbering.xml`, `w:numPr`, atau override
`numId=0` memerlukan ADR baru. Dokumen ini menjelaskan kontrak teknisnya; ADR
memuat alasan dan alternatif yang ditolak.

## `numbering.py`

`numbering.py` adalah satu sumber konversi angka Romawi:

- `roman_to_int` mengubah token Romawi menjadi bilangan bulat;
- `to_roman` memformat bilangan bulat menjadi angka Romawi kapital.

Pembacaan nomor bab dari teks (`chapter_number`) sudah dihapus. Nomor bab
sekarang dihitung dari urutan heading bernomor di dokumen.

## `native_numbering.py`

`native_numbering.py` menulis numbering native:

- `word/numbering.xml` dengan satu `w:abstractNum` dan satu `w:num` berisi
  level 1-3 yang terhubung ke `Heading1`..`Heading3`;
- `w:numPr` pada style `Heading1`..`Heading3` dan `numId=0` pada style judul
  daftar isi (`format.toc_heading.heading_style`);
- content type dan relationship `numbering.xml` bila belum ada.

Id **dialokasikan dinamis** dari rentang yang masih bebas:
`abstractNumId < 990` dan `numId < 1000` (Pandoc membuang entri reference di
luar batas itu; reference stok memakai 990/1000 untuk bullet). Id yang sudah
dipakai list lain tidak pernah ditimpa; bila tidak ada id bebas, build gagal
dengan `NumberingError`. Verifikasi juga memastikan tidak ada `w:num` lain
yang menunjuk abstract heading. Level definition mengikuti
`structure.numbering`:

| `numbering.body` | `lvlText` level 1 | `numFmt` | `suff` |
| --- | --- | --- | --- |
| `BAB_ROMAN` | `BAB %1` | `upperRoman` | `nothing` |
| `ARABIC_DOTTED` | `%1.` | `decimal` | `space` |

Level 2 memakai `%1.%2` dan level 3 `%1.%2.%3`; titik akhir mengikuti
`sub_dot`/`subsub_dot`. `w:isLgl` dipasang pada level 2-3 agar `%1` tampil
desimal (`1.1`, bukan `I.1`). Label level 1 tidak memakai separator karena
judul H1 diawali `w:br` (lihat `markdown/headings.py`), sehingga nomor dan
judul tetap dua baris.

`verify_heading_numbering` memeriksa part, content type, relationship,
definisi level, dan `w:numPr` style; reference tanpa plumbing yang lengkap
gagal dengan `NumberingError`. Verifikasi dijalankan pada reference turunan
dan pada output setelah Pandoc (stage `sections`).

## `heading_numbering.py`

`heading_numbering.py` menangani iterasi heading dan heading unnumbered:

- `iter_headings` membaca heading body berurutan;
- `classify_chapters` memetakan H1/`ChapterTitle` ke front matter, body,
  back matter, atau unnumbered memakai `structure.body` (judul bab berurutan),
  keberadaan `structure.back_matter`, dan status numbering; `iter_chapter_candidates`/`iter_chapter_headings`
  menjadi sumber tunggal untuk section, TOC, caption, dan persamaan;
- `is_numbered_heading` membaca override `numId=0` lebih dulu dan jatuh ke
  `is_unnumbered` bila override belum ada;
- `apply_heading_numbering` memasang override `w:numPr` `numId=0` pada
  heading tak bernomor, H2/H3 sebelum H1 bernomor, dan H2/H3 di bawah H1
  tak bernomor. Tidak ada run atau teks heading yang dibangun ulang.

Batas `.unnumbered`: atribut `{.unnumbered}`/`{-}` dari Markdown dibuang
Pandoc, jadi status unnumbered tidak terbawa ke DOCX. Untuk dokumen nyata,
klasifikasi memakai `structure.body` dan urutan heading; marker hanya berguna
pada fixture DOCX langsung.

`numId=0` adalah satu-satunya cara mematikan numbering level style per
paragraf; Pandoc tidak dapat menuliskannya dari Markdown.

## Heading Markdown

`markdown/headings.py` tidak menulis nomor. `finalize_markdown_headings`
hanya:

- meng-uppercase judul H1 bernomor;
- menyisipkan raw inline `<w:br/>` sebelum judul H1 `BAB_ROMAN`;
- membiarkan H2-H6 dan heading `unnumbered` apa adanya.

Header body hanya memuat field `PAGE`; tidak ada field header berjalan.
Nomor dan judul bab tetap berasal dari numbering native dan teks heading.

## Caption dan persamaan

`captions.py` dan `stages/equations.py` menghitung nomor bab dari **jumlah
heading bernomor dalam urutan dokumen**, bukan dari teks. Keduanya memakai
`classify_chapters` yang sama dan menerima `ChapterTitle`, sehingga caption
dan persamaan tidak lagi berbeda dalam mengenali bab. Caption tetap memakai
`SEQ` + prefix literal; nomor persamaan `(bab.n)` tetap literal.

## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [sections.md](sections.md) untuk batas section dan header/footer.
- [paragraphs.md](paragraphs.md) untuk helper level heading.
- [captions.md](captions.md) untuk nomor bab pada caption.
- [fields.md](fields.md) untuk daftar field native.
- [../pipeline/stages.md](../pipeline/stages.md) untuk stage `numbering`.

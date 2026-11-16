# Style

Halaman ini menjelaskan style inti yang dipakai pipeline dan asal
`reference.docx`. Kontrak style ada di
[contracts/docx.md](../../contracts/docx.md).

Style inti yang dipakai pipeline:

- `Normal`, `Heading1` sampai `Heading9`;
- `TOCHeading`, `TOC1`, `TOC2`, `TOC3`;
- `Caption`, `TableCaption`, `ImageCaption`, `Figure`;
- `Bibliography`, `SourceCode`, `VerbatimChar`, `HTMLCode`,
  `HTMLPreformatted`;
- `IstilahAsing`, `IstilahReview`;
- style sampul seperti `CoverTitle`, `CoverSubtitle`, `CoverName`,
  `CoverInstitution`, dan `CoverImage`.

`style_reference` menghasilkan `reference.docx` turunan dari `format.yaml`.
Sumber `reference.docx` di `src/autooffice/docx/data/` tidak pernah ditimpa.

## Numbering heading

Style `Heading1`..`Heading3` membawa `w:numPr` ke `numId` hasil alokasi dinamis yang didefinisikan
di `word/numbering.xml` turunan. Level 1 memakai `BAB %1` (`upperRoman`) atau
`%1.` (`decimal`) sesuai `structure.numbering`; level 2-3 memakai
`%1.%2`/`%1.%2.%3` dengan `w:isLgl`. `TOCHeading` wajib `numId=0` agar judul
daftar isi tidak ikut menjadi bab. Detail ada di
[numbering.md](numbering.md).

## Blok kode monokrom

Blok kode wajib hitam-putih mengikuti format kampus. Stage `pandoc` menjalankan
Pandoc dengan `--syntax-highlighting=none`, jadi Pandoc **tidak** menulis
`KeywordTok`, `StringTok`, `CommentTok`, atau style token `*Tok` lain, dan
reference turunan tidak mendeklarasikan satu pun style token tersebut.
`word/styles.xml` hanya berisi style yang dibutuhkan pipeline; blok kode tetap
memakai `SourceCode` dan kode sebaris tetap memakai `VerbatimChar`.

Bila kelak blok kode ingin berwarna, hapus flag tersebut dan tambahkan kembali
31 style token Pandoc 3.13 ke reference turunan (mis. lewat `format.yaml`)
sebelum mengaktifkan highlighting. Tanpa deklarasi itu Pandoc akan mengimpor
style token sendiri sehingga `word/styles.xml` tidak lagi ditentukan
`format.yaml`. Bila Pandoc menambah style baru, `tests/docx/test_style_parity.py`
gagal dan menyebut `styleId` yang belum dideklarasikan.


## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [package.md](package.md) untuk part `word/styles.xml`.
- [fields.md](fields.md) untuk field yang memakai style TOC.
- [terms.md](terms.md) untuk style `IstilahAsing` dan `IstilahReview`.
- [../formats.md](../formats.md) untuk `format.yaml`.

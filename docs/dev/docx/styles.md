# Style

Halaman ini menjelaskan style inti yang dipakai pipeline dan asal
`reference.docx`. Kontrak style ada di
[contracts/docx.md](../../contracts/docx.md).

Style inti yang dipakai pipeline:

- `Normal`, `Heading1` sampai `Heading5`;
- `TOCHeading`, `TOC1`, `TOC2`, `TOC3`;
- `Caption`, `TableCaption`, `ImageCaption`, `Figure`, `TableofFigures`;
- `AbstractBody`, `AbstractKeywords`;
- `Bibliography`, `SourceCode`, `VerbatimChar`;
- `IstilahAsing`, `IstilahReview`;
- style sampul seperti `CoverTitle`, `CoverSubtitle`, `CoverName`,
  `CoverInstitution`, dan `CoverImage`.

Style `AbstractBody`, `AbstractKeywords`, `IstilahAsing`, `IstilahReview`, dan
`TableofFigures` dibekukan di `reference.docx` sumber. `style_reference` dan
stage terkait hanya memverifikasi nilainya, tidak menulis ulang.

`style_reference` menghasilkan `reference.docx` turunan dari `format.yaml`.
Sumber `reference.docx` di `src/autooffice/docx/data/` tidak pernah ditimpa.

## Style yang sengaja dihapus

`reference.docx` sumber **bukan lagi salinan stok Pandoc**. Sebanyak 12 style
dihapus secara sengaja dari `word/styles.xml` (63 menjadi 51 style dasar):

- `Heading6`, `Heading7`, `Heading8`, `Heading9` (paragraf) beserta
  `Heading6Char`, `Heading7Char`, `Heading8Char`, `Heading9Char` (karakter);
- `DefinitionTerm` dan `Definition` (paragraf);
- `HTMLPreformatted` (paragraf) dan `HTMLCode` (karakter).

`style_reference` juga tidak mendeklarasikan ulang `HTMLPreformatted` dan
`HTMLCode`. `w:latentStyles` dibiarkan apa adanya. `FootnoteText`,
`FootnoteBlockText`, dan `FootnoteReference` tetap dipertahankan karena
catatan kaki masih didukung.

Konsekuensi: dokumen yang memakai heading level 6+, definition list, atau blok
HTML mentah akan **gagal** di gate parity
(`tests/docx/test_style_parity.py`). Pandoc memakai atau mengimpor style yang
tidak ada di reference dan `test_pandoc_imports_no_style_outside_reference`
menyebut `styleId` yang hilang. Tambahkan style itu kembali ke `reference.docx`
(dan ke `style_specs_for_format` bila perlu) bila konstruksinya memang
didukung.

Setelah 12 style dihapus, lima style yang sebelumnya ditulis saat build
dibekukan ke source: `AbstractBody`, `AbstractKeywords`, `IstilahAsing`,
`IstilahReview`, dan `TableofFigures`. Source kini memuat 56 style; derived
reference dan output mempertahankan jumlah itu.

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

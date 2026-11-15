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

## Style token syntax highlighting

Pandoc menulis satu style karakter per token syntax highlighting (mis.
`KeywordTok`, `StringTok`, `CommentTok`). Tanpa deklarasi di reference
turunan, Pandoc mengimpor seluruh style token itu sendiri sehingga
`word/styles.xml` tidak lagi ditentukan `format.yaml`. Karena itu
`style_reference` selalu mendeklarasikan `PANDOC_HIGHLIGHT_STYLES` (31 style
token Pandoc 3.13) dengan `basedOn` `VerbatimChar`.

Properti warna/bold/italic diambil dari `code.highlight` di `format.yaml`.
Token tanpa entri mewarisi font dan warna `code.font` (monokrom). Bila Pandoc
kelak menambah style baru, `tests/docx/test_style_parity.py` gagal dan
menyebut `styleId` yang belum dideklarasikan.


## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [package.md](package.md) untuk part `word/styles.xml`.
- [fields.md](fields.md) untuk field yang memakai style TOC.
- [terms.md](terms.md) untuk style `IstilahAsing` dan `IstilahReview`.
- [../formats.md](../formats.md) untuk `format.yaml`.

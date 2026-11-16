# ADR 0018: Pensiunkan Style yang Tidak Dipakai dan Matikan Syntax Highlighting

- Status: diterima
- Tanggal: 2026-11-16
- Pemilik: DOCX owner
- Rujukan: [ADR 0015](0015-native-heading-numbering.md),
  [kontrak DOCX](../contracts/docx.md),
  [style DOCX](../dev/docx/styles.md),
  [format dan struktur](../dev/formats.md), dan
  [format dokumen pengguna](../user/document-format.md)

## Konteks

Audit style pada rilis 4.0.0 menemukan **77 dari 99 style** di
`word/styles.xml` output tidak pernah dirujuk oleh dokumen. Style itu ikut
terbawa karena `reference.docx` dan `style_reference` mendeklarasikan katalog
Pandoc, bukan karena konstruksi dokumen benar-benar memakainya. Dua kelompok
yang paling jelas tidak menghasilkan output adalah style token syntax
highlighting dan style untuk konstruksi yang tidak didukung format kampus.

Pandoc 3.13 sebenarnya menulis token syntax highlighting (`KeywordTok`,
`StringTok`, `CommentTok`, dan 28 token lain) ketika highlighting aktif.
Namun token itu **tidak pernah sampai ke output** karena stage `code`
membangun ulang setiap baris dari teks saja:

- `package/tables.py` meratakan paragraf kode menjadi `_Line` yang hanya
  menyimpan `text: str` dan marker bookmark/comment. `w:rStyle` pada run
  token tidak disalin.
- `_make_code_paragraph` membuat run baru dari `line.text` dengan `rPr`
  seragam dari `CodeSpec`; `rStyle` milik Pandoc dibuang.

Akibatnya palet 31 entri `code.highlight` di `format.yaml` dan
`config/highlight.py` tidak berefek apa pun. Warna, bold, dan italic token
tidak pernah terlihat, sementara 31 deklarasi style tetap membebani
`word/styles.xml` dan gate parity.

Kelompok kedua adalah style yang tidak mungkin muncul di dokumen kampus:
`Heading6`-`Heading9` beserta pasangan karakter `Heading6Char`-`Heading9Char`,
`DefinitionTerm`/`Definition`, dan `HTMLPreformatted`/`HTMLCode`. Pandoc 3.13
bahkan membuang blok HTML mentah untuk output DOCX, sehingga `HTMLPreformatted`
dan `HTMLCode` tidak dipakai. Definition list dan heading level 6+ juga bukan
bagian model dokumen yang didukung.

## Keputusan

1. **Blok kode selalu monokrom.** `build_pandoc_command` menambahkan
   `--syntax-highlighting=none` secara eksplisit. Tag bahasa pada fence tidak
   mengaktifkan warna; blok kode memakai `SourceCode`, kode sebaris memakai
   `VerbatimChar`, dan teks tetap hitam sesuai format kampus.
2. **Hapus jalur konfigurasi highlighting.** Blok `code.highlight` (31 entri)
   dihapus dari `format.yaml`. `CodeFormat.highlight`, `CodeHighlightToken`,
   `_parse_highlight`, `config/highlight.py` beserta
   `PANDOC_HIGHLIGHT_STYLES`, dan `_highlight_specs` dihapus. Key
   `code.highlight` tidak lagi dikenal dan ditolak sebagai error konfigurasi.
3. **Pensiunkan 12 style.** Kedua belas style dihapus dari `reference.docx`
   sumber:

   | Jenis | Style |
   | --- | --- |
   | Paragraf | `Heading6`, `Heading7`, `Heading8`, `Heading9`, `DefinitionTerm`, `Definition`, `HTMLPreformatted` |
   | Karakter | `Heading6Char`, `Heading7Char`, `Heading8Char`, `Heading9Char`, `HTMLCode` |

   `_CODE_STYLE_TYPES` tidak lagi mendeklarasikan `HTMLPreformatted` dan
   `HTMLCode`. `w:latentStyles` dibiarkan apa adanya.
4. **Pertahankan tiga style catatan kaki.** `FootnoteText`,
   `FootnoteBlockText`, dan `FootnoteReference` tetap ada karena catatan kaki
   adalah fitur akademik standar dan biayanya hanya tiga style.
5. **Perkuat gate parity.** `tests/docx/test_style_parity.py` sekarang menolak
   dua arah pelanggaran: style yang **diimpor** Pandoc tetapi tidak ada di
   reference, dan style yang **dipakai** output (`w:pStyle`, `w:rStyle`,
   `w:tblStyle` pada `document.xml` dan `footnotes.xml`) tetapi tidak
   dideklarasikan reference. Gate juga memastikan reference, spec, dan output
   tidak memuat style `*Tok`, style pensiunan tidak muncul lagi, dan tiga
   style footnote tetap tersedia.

## Alternatif yang ditolak

- **Memperbaiki stage `code` agar mempertahankan `rStyle` sehingga
  highlighting hidup.** Ditolak karena format kampus menuntut teks hitam.
  Perbaikan itu menambah model fragmen run, penyalinan `rPr` per token, dan
  test paritas baru untuk fitur yang tidak boleh dipakai.
- **Menghapus seluruh 77 style yang tidak dipakai.** Ditolak karena style yang
  hilang membuat Pandoc mengimpor definisinya sendiri saat konstruksi muncul.
  Kegagalannya tidak terlihat saat build normal, tetapi muncul belakangan
  sebagai drift `word/styles.xml` atau kegagalan parity pada dokumen lain.
  Yang dipensiunkan dibatasi pada style yang terbukti tidak dapat dipakai.
- **Menghapus `Footnote*` juga.** Ditolak karena catatan kaki masih dipakai
  dokumen akademik. Menghapusnya akan menggagalkan dokumen yang sah hanya
  untuk menghemat tiga style.

## Konsekuensi

- Dokumen dengan heading level 6+, definition list, atau blok HTML mentah
  **gagal** di gate parity. Pesan gate menyebut `styleId` yang tidak ada di
  reference; menambahkan style itu kembali ke `reference.docx` adalah
  perubahan sadar yang memerlukan ADR baru.
- `format.yaml` yang masih memuat key `code.highlight` **ditolak** sebagai
  error konfigurasi. Key itu harus dihapus, bukan dibiarkan kosong.
- Reference sumber menyusut dari **63 menjadi 51 style**; output menyusut dari
  **99 menjadi 56 style**. Jumlah itu berasal dari 31 token highlighting dan
  12 style pensiunan, bukan dari penghapusan style yang masih dipakai.
- Untuk mengaktifkan kembali highlighting, tiga hal harus dilakukan bersamaan:
  hapus `--syntax-highlighting=none`, tambahkan 31 style token ke reference
  turunan, dan perbaiki stage `code` agar mempertahankan `rStyle`. Melakukan
  hanya salah satunya menghasilkan style yang diimpor Pandoc atau token yang
  tetap dibuang.
- Style inti lain tidak berubah: `Normal`, `Heading1`-`Heading5`, style TOC,
  caption, `SourceCode`, `VerbatimChar`, `Bibliography`, istilah, dan style
  sampul tetap dideklarasikan.

## Bukti

| Metrik | Sebelum | Sesudah |
| --- | ---: | ---: |
| Halaman dokumen uji | 21 | 21 |
| Heading + caption identik di Word | 36/36 | 36/36 |
| Style dasar `reference.docx` | 63 | 51 |
| Style output | 99 | 56 |
| Suite test | — | 3.552 lulus |
| Coverage global | — | 90,57% |
| LOC bersih perubahan | — | -242 |

- Dua build berturut-turut menghasilkan sha256 yang sama.
- Perubahan highlighting tidak mengubah `document.xml`; perubahan style
  pensiunan hanya menyentuh deklarasi style dan fixture yang memancing
  konstruksi pensiunan.
- Gate parity dijalankan pada fixture `kitchen-sink` yang tetap memuat blok
  kode berbahasa, footnote, tabel, caption, sitasi, dan format inline.
- LOC -242 baris diukur dari diff perubahan highlighting
  (`a7d6801`): 69 baris ditambah, 311 baris dihapus.
- Perubahan style pensiunan tercatat di `50ae272`; perubahan highlighting
  tercatat di `a7d6801`. Keduanya dirilis sebagai 4.0.0 pada `3a21c63`.

## Status

Diterima. Mengaktifkan kembali syntax highlighting, menambah kembali style
yang dipensiunkan, atau melonggarkan gate parity memerlukan ADR baru. Bug
footer Romawi front matter yang tercatat di ADR 0015 tetap menjadi pekerjaan
lanjutan dan tidak berubah oleh ADR ini.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)

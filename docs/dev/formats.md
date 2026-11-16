# Format dan Struktur

Format mengatur rupa dokumen. Struktur mengatur urutan bab, penomoran, flag
TOC, dan daftar. Keduanya adalah data paket di `src/autooffice/docx/data/` dengan
skema tertutup. Kontrak DOCX ada di
[contracts/docx.md](../contracts/docx.md).

## Daftar isi

- [Lokasi](#lokasi)
- [`format.yaml`](#formatyaml)
- [`structure.yaml`](#structureyaml)
- [Struktur yang tersedia](#struktur-yang-tersedia)
- [Front matter `document.md`](#front-matter-documentmd)
- [Validasi](#validasi)
- [Referensi resmi](#referensi-resmi)

## Lokasi

```text
src/autooffice/docx/data/
|-- formats/
|   `-- undip-msi/
|       |-- format.yaml
|       |-- citation.csl
|       |-- logo.jpg
|       `-- reference.docx
|-- structures/
|   |-- assignment/structure.yaml
|   |-- proposal/structure.yaml
|   `-- thesis/structure.yaml
`-- glossary/istilah.tsv
```

ID adalah nama direktori. `format` di `format.yaml` dan `structure.yaml` harus
sama dengan nama direktori.

## `format.yaml`

Top-level key:

| Key | Isi |
| --- | --- |
| `format` | ID format. |
| `name`, `description` | Nama dan deskripsi tampilan. |
| `page` | Ukuran, orientasi, margin, jarak header/footer, dan gutter. |
| `font` | Font body dan monospace. |
| `abstract` | Font dan spasi isi abstrak serta kata kunci. |
| `headings` | Style `heading1`, `heading2`, `heading3`. |
| `toc_heading` | Style judul daftar isi. |
| `captions` | Label, separator, font, dan keep-next caption gambar/tabel. |
| `figures` | Perataan caption/gambar dan spacing. |
| `code` | Font, border, shading, tabel kode, dan style deteksi. |
| `bibliography_style` | Judul dan format daftar pustaka. |
| `citation` | `csl`, `bibliography`, dan `locale`. |
| `assets` | `logo` dan `reference_docx`. |

Blok `abstract` mengatur font dan spasi isi abstrak serta kata kunci.
`abstract.english_italic` (boolean) menentukan apakah style `AbstractBodyEn`
untuk abstrak Inggris membawa `w:i`/`w:iCs`; bahasa paragrafnya tetap
`en-US`. Style itu dibekukan di `reference.docx` sumber, jadi nilainya
diverifikasi saat build: mengubahnya berarti mengubah `word/styles.xml`
sumber juga.

Blok kode selalu monokrom. Pandoc dijalankan dengan
`--syntax-highlighting=none`, sehingga tidak menulis token `KeywordTok`,
`StringTok`, atau style token lain. `format.yaml` tidak punya key
`code.highlight`; `code.font`, `code.border`, dan `code.table` tetap mengatur
tampilan tabel kode. Bila kelak blok kode ingin berwarna, aktifkan kembali
flag highlighting dan tambahkan deklarasi 31 style token ke `reference.docx`
turunan.

Semua dimensi memakai satuan `cm`, `mm`, `in`, `pt`, atau `twip`. Semua warna
memakai enam digit heksadesimal. Key `presets`, `preset`, dan `margin_preset`
tidak dikenal dan menghasilkan error migrasi.

### Format `undip-msi`

Nilai final:

- Halaman A4 portrait, margin atas 4 cm, bawah 3 cm, kiri 4 cm, kanan 3 cm.
- Body Times New Roman 12 pt, spasi 1,5, justify, first line indent 1,25 cm.
- Isi abstrak dan kata kunci Times New Roman 10 pt, spasi 1,0.
- Abstrak Inggris memakai style `AbstractBodyEn` (italic, `en-US`); kata kunci
  memakai style karakter `AbstractKeywordText`.
- Heading 1 rata tengah, bold, 12 pt. Heading 2 dan 3 bold, 12 pt, indent
  gantung 1,25 cm.
- Caption gambar dan tabel Times New Roman 10 pt, spasi 1,0.
- Heading memakai numbering native Word (`BAB I`, `1.1`, `1.1.1`); header body
  tidak memuat teks judul bab.
- Kode Courier New 10 pt dalam tabel 1x1 dengan border penuh.
- Sitasi memakai `citation.csl` dan `references.bib`.
- Aset memakai `logo.jpg` dan `reference.docx`.

## `structure.yaml`

Front matter tidak lagi didaftarkan di `structure.yaml`. Sampul, lembar
pengesahan, pernyataan, kata pengantar, abstrak, dan kata kunci ditulis
langsung di `document.md`; lihat [Front matter `document.md`](#front-matter-documentmd).

Top-level key:

| Key | Isi |
| --- | --- |
| `format` | Format default untuk struktur ini. |
| `toc` | Tulis field TOC native bila `true`. |
| `lists` | `figures`/`tables`: tulis daftar tabel/gambar bila `true`. |
| `body` | Daftar bab logis. |
| `back_matter` | Daftar bagian setelah body. |
| `numbering` | Format nomor Heading 1/2/3. |

Key lain adalah error, termasuk `front_matter` dan `cover` yang sudah dihapus.
`body` minimal satu entri.

`toc` dan `lists` adalah flag tampilan, bukan penanda urutan. Field TOC selalu
diletakkan sebelum Heading 1 bernomor pertama oleh stage `toc`. Daftar ditulis
oleh stage `lists` dengan urutan tetap: daftar tabel lalu daftar gambar.
Daftar memakai field `TOC \c` dan caption memakai field `SEQ` bila aktif.

### `body`

`body` adalah urutan bab logis, bukan path berkas. Setiap entri menghasilkan
tepat satu Heading 1. Judul entri dibandingkan case-insensitive setelah spasi
dirapatkan; tanda baca signifikan.

```yaml
body:
  - {id: pendahuluan, title: "Pendahuluan"}
  - {id: tinjauan-pustaka, title: "Tinjauan Pustaka"}
```

Heading 1 tambahan ditolak, kecuali `# Lampiran` yang dideklarasikan
`back_matter`.

### `back_matter`

| ID | Source | Isi |
| --- | --- | --- |
| `bibliography` | `generated` | Daftar pustaka dari CSL dan `.bib`. |
| `appendices` | `document` | Bagian `# Lampiran` di akhir dokumen. |

Jika `appendices` ada, `document.md` wajib memuat tepat satu `# Lampiran`
setelah bab terakhir. Jika `bibliography` ada, berkas `.bib` wajib ada.

### `numbering`

| Nilai `body` | Heading 1 | Heading 2 | Heading 3 |
| --- | --- | --- | --- |
| `BAB_ROMAN` | `BAB I` + baris baru + judul kapital | `1.1.` + tab + judul | `1.1.1.` + tab + judul |
| `ARABIC_DOTTED` | `1.` + spasi + judul kapital | `1.1.` + tab + judul | `1.1.1.` + tab + judul |

`sub_dot` dan `subsub_dot` mengatur titik akhir nomor subbab. Nomor bab selalu
mengikuti `numbering.body`.

## Struktur yang tersedia

### `assignment`

- Front matter: ditulis di `document.md` (sampul saja pada contoh).
- Body: Pendahuluan, Pembahasan, Penutup.
- Back matter: bibliography.
- `toc: false`; daftar tabel/gambar tidak aktif.
- Numbering: `ARABIC_DOTTED`.

### `proposal`

- Front matter: ditulis di `document.md` (sampul dan halaman persetujuan).
- Body: Pendahuluan, Tinjauan Pustaka, Metode Penelitian, Jadwal Penelitian.
- Back matter: bibliography.
- `toc: true`; daftar tabel/gambar tidak aktif.
- Numbering: `ARABIC_DOTTED`.

### `thesis`

- Front matter: ditulis di `document.md` (sampul, lembar pengesahan,
  pernyataan, kata pengantar, abstrak Indonesia/Inggris, kata kunci).
- Body: Pendahuluan, Tinjauan Pustaka, Metodologi, Hasil dan Pembahasan,
  Penutup.
- Back matter: bibliography, appendices.
- `toc: true`; daftar tabel dan gambar aktif.
- Numbering: `BAB_ROMAN`.

## Front matter `document.md`

Blok YAML di awal berkas hanya memuat metadata dokumen. Kunci yang tetap
divalidasi adalah `title`, `author`, dan `nim` bila ada. `report_name`,
`structure`, dan `format` tetap wajib karena menentukan nama keluaran dan
konfigurasi build. Kunci identitas dan abstrak lama (`subtitle`, `lecturer`,
`lecturer_label`, `course`, `institution`, `faculty`, `year`, `date`,
`preface`, `abstract_id`, `abstract_en`, `keywords`, `keywords_en`) diterima
sebagai metadata opsional, tetapi tidak lagi dirender menjadi Markdown.

Isi visual front matter ditulis langsung sebagai Markdown setelah blok YAML:

````markdown
::: {custom-style="CoverTitle"}
JUDUL LAPORAN\
SUBJUDUL LAPORAN
:::

::: {custom-style="CoverImage"}
![](logo.jpg){width=4.88cm}
:::

\

<!-- section-break -->

# LEMBAR PENGESAHAN {-}

**Judul:** Judul Laporan

November 2026

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# ABSTRAK {-}

::: {custom-style="AbstractBody"}
Isi abstrak.
:::

::: {custom-style="AbstractKeywords"}
**Kata Kunci:** [Markdown, Pandoc]{custom-style="AbstractKeywordText"}
:::
````

Aturan front matter Markdown:

| Bagian | Bentuk |
| --- | --- |
| Sampul | `custom-style` `CoverTitle`, `CoverSubtitle`, `CoverCourse`, `CoverLecturer`, `CoverLine`, `CoverName`, `CoverInstitution`, dan `CoverImage`. |
| Logo sampul | `![](logo.jpg){width=...cm}`; path dicari di direktori dokumen lalu direktori format. Alt text boleh kosong karena logo dekoratif. |
| Jarak vertikal sampul | baris `\` (hard line break), bukan `spacer()` atau paragraf kosong. |
| Section break penutup sampul | marker `<!-- section-break -->` pada baris sendiri. |
| Halaman baru | blok raw OpenXML berisi `w:br w:type="page"`. |
| Lembar pengesahan/pernyataan | Heading 1 `{-}` diikuti paragraf atau tabel biasa. |
| Kata pengantar/abstrak | Heading 1 `{-}` diikuti paragraf. |
| Abstrak Inggris | div `::: {custom-style="AbstractBodyEn" lang="en-US"}`. |
| Kata kunci | div `::: {custom-style="AbstractKeywords"}` dan span `[teks]{custom-style="AbstractKeywordText"}`. |

Stage `front_matter` mengganti setiap baris `<!-- section-break -->` dengan raw
OpenXML `w:sectPr`; ukuran halaman, margin, jarak header/footer, dan gutter
berasal dari `format.yaml`. Stage yang sama tetap menyiapkan Heading 1 body
(uppercase dan `w:br` untuk `BAB_ROMAN`) serta menandai `# Lampiran` sebagai
unnumbered.

Heading sebelum Heading 1 bab pertama adalah front matter dan wajib memakai
`{-}` (atau `.unnumbered`). Heading body tetap mengikuti urutan `body` dan
tidak boleh ditulis bernomor. Marker `<!-- toc -->` belum dipakai pada fase
ini; TOC tetap disisipkan oleh stage `toc` sebelum Heading 1 bernomor pertama.

Kunci lama seperti `preset`, `daftar_gambar`, `daftar_tabel`, `approval`,
`statement`, `references`, `csl`, `reference-doc`, `template`, dan `cover`
ditolak dengan pesan migrasi. Kunci `toc` di front matter dokumen juga ditolak
sebagai kunci tidak dikenal (`CFG-UNKNOWN-KEY`).

## Validasi

`load_project` memvalidasi:

- front matter dan tipe YAML;
- keberadaan format dan struktur;
- aset gambar, bibliografi, dan glosarium;
- urutan Heading 1 terhadap `body` (heading front matter wajib `{-}`);
- lampiran terhadap `back_matter`;
- caption Markdown pada body, bukan pada front matter.

Error menyebut path dan key. `check` mengembalikan exit code 1 untuk semua
error konfigurasi.

## Referensi resmi

Label registry yang dipakai halaman ini: `ruamel.yaml documentation`. URL
resminya ada di [registry referensi](references.md).

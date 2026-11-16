# Design System AutoOffice

Halaman ini menjelaskan cara token, theme, font, dan kontras bekerja di deck
AutoOffice. Kontrak normatifnya ada di
[kontrak design token](../contracts/design-token.md); halaman ini adalah
panduan konsep dan contoh pemakaian.

## Daftar Isi

- [Alur token](#alur-token)
- [Token dasar](#token-dasar)
- [Theme](#theme)
- [Font](#font)
- [Tipografi per peran](#tipografi-per-peran)
- [Card metric dan quote](#card-metric-dan-quote)
- [Tabel, code, dan chart](#tabel-code-dan-chart)
- [Kontras](#kontras)
- [Known gap](#known-gap)
- [Aturan implementasi](#aturan-implementasi)

## Alur token

Token adalah data package, bukan berkas kerja pengguna:

```text
src/autooffice/design/data/tokens.yaml   token dasar
src/autooffice/design/data/themes.yaml   override warna per theme
        |
        v
autooffice.design.theme.resolve_theme(name)
        |
        v
Theme immutable -> layout engine dan renderer
```

Renderer hanya menerima `Theme` yang sudah di-resolve. Renderer tidak membaca
nama theme atau nilai heksadesimal sendiri.

```python
from autooffice.design import resolve_theme

theme = resolve_theme("hitam")
print(theme.name)  # hitam
print(theme.mode)  # light
print(theme.colors.accent)  # #111827
print(theme.colors.background)  # #FAFAFA
print(len(theme.chart.series))  # 4
```

Nama theme yang tidak dikenal melempar `DesignTokenError` dengan daftar theme
yang tersedia. Default `resolve_theme()` adalah `indigo`.

## Token dasar

`tokens.yaml` memuat kategori berikut:

| Kategori | Isi | Contoh |
| --- | --- | --- |
| Warna | background, surface, ink, muted, border, aksen, status | `ink: #0B0B0F` |
| Tipografi | family, weight, ukuran pt per peran, line-height, tracking | display 44 pt, title 30 pt, body 16.5 pt |
| Grid | 12 kolom, gutter, margin, row gap, kanvas 16:9 | 12192000 x 6858000 EMU |
| Spacing | `sm`, `md`, `lg`, padding kartu, divider | `sm_emu: 45720` |
| Radius | `sm`, `md`, `lg` | `md_emu: 91440` |
| Card | fill, padding, radius card konten | `#E5E7EB`, 228600 EMU, 91440 EMU |
| Shadow | kartu, overlay, `none` | `0 1 2 0 rgba(17, 24, 39, 0.08)` |
| Chart | empat warna seri, grid, axis, legend, title | lihat bagian theme |
| Code | family mono, ukuran, filename, line-height | `ui-monospace, ...`, 12 pt |

Ukuran memakai integer EMU supaya renderer tidak menulis angka baru. Satu
piksel kanvas sama dengan 9525 EMU. Kanvas 1280 x 720 px menjadi
12192000 x 6858000 EMU.

## Theme

Hanya ada dua theme produk. Keduanya mode `light`; `hitam` bukan dark theme.

| Theme | Aksen | Kanvas | Cover |
| --- | --- | --- | --- |
| `indigo` (default) | `#4F46E5` | `#FAFAFA` | `#4F46E5` -> `#4338CA` -> `#312E81` |
| `hitam` | `#111827` | `#FAFAFA` | `#111827` -> `#0B1220` -> `#000000` |

Theme hanya mengubah warna. Geometri grid, spacing, radius, shadow,
tipografi, dan code tetap sama di kedua theme. `hitam` tidak memakai palet
`malam`.

Warna chart memakai empat slot di kedua theme:

| Theme | `chartSeries` |
| --- | --- |
| `indigo` | `#4F46E5`, `#0F766E`, `#B45309`, `#BE123C` |
| `hitam` | `#111827`, `#374151`, `#4B5563`, `#6B7280` |

Palet kategorikal mentah `hitam` dari baseline desain deck memuat `#9CA3AF`
dan `#D1D5DB` yang tidak lolos 3:1 di kanvas terang. Karena itu AutoOffice
memakai turunan empat warna di atas. Batas empat slot berlaku untuk seri
`bar`/`line` dan kategori `donut`.

## Font

Deck memakai satu family: `Arial` weight 400, 600, 700, dan 800. Family dan
weight disimpan di token typography; tidak ada embedding font ke PPTX.

```yaml
typography:
  family: "Arial"
  weights: [400, 600, 700, 800]
```

Weight token benar-benar dipakai. Pemetaan peran terpusat di
`measure.role_typography`, dan renderer `textbox.role_style` memanggil fungsi
yang sama. `body_style`, bullets, dan notes juga mengambil bobot body dari
`weights[0]`; tidak ada lagi tabel bobot hardcoded `_ROLE_WEIGHTS` atau default
literal `weight=400` di renderer maupun salinannya di measure.

Pengukuran layout memakai Liberation Sans, font metrik-kompatibel Arial. Dua
berkas TTF Liberation Sans (Regular dan Bold) serta lisensi SIL Open Font
License 1.1 dibundel di `src/autooffice/assets/fonts/liberation-sans/` hanya
untuk pengukuran. Berkas itu tidak ditanam ke PPTX dan tidak dipakai sebagai
family tampilan.

Konsekuensi platform:

- Di Windows dan macOS, Arial umumnya tersedia sehingga PPTX tampil sesuai
  pengukuran.
- Di Android, Linux, atau lingkungan tanpa Arial, PowerPoint, Google Slides,
  LibreOffice, atau aplikasi lain dapat mengganti Arial dengan Liberation Sans
  atau font substitusi. Tata letak umumnya tetap sama karena metrik
  kompatibel, tetapi bentuk glyph dan rendering dapat berbeda.
- Bila PDF harus tampil identik di semua perangkat, aktifkan embedding font
  saat mengekspor dari PowerPoint atau Word. AutoOffice tidak menanam font.

DOCX tidak memakai design system deck; DOCX mempertahankan font format
baseline DOCX. Google Slides memakai nama family `Arial` dan dapat melakukan
substitusi font sesuai lingkungan Google.

## Tipografi per peran

Ukuran aktif berasal dari `tokens.yaml`:

| Peran | Ukuran | Bobot |
| --- | --- | --- |
| `display` | 44 pt | 800 |
| `title` | 30 pt; 43.5 pt hanya pada `role_typography(layout_id="cover")`, belum dipakai produksi | 700 |
| `lead` | 18 pt | 600 |
| `body` | 16.5 pt | 400 |
| `caption` | 12.5 pt | 400 |
| `label` | 14 pt | 600 |
| `kicker` | 12.5 pt dengan tracking 0.08 em | 700 |
| Metric value | 42 pt | 800 |
| Minimum | 10 pt | — |

- `cover_title_pt` 43.5 pt sudah ada dan ter-resolve, tetapi belum dipakai
  geometri produksi; build masih memakai `title_pt` 30 pt untuk judul cover.
  Lihat [Known gap](#known-gap).
- Metric default berwarna `ink`. Hanya status `success`, `warning`, dan
  `danger` yang memakai warna status; `neutral` kembali ke `ink`.
- Tier `caption` 12.5 pt warna `muted` dipakai role `caption` pada block teks,
  misalnya keterangan kecil atau credit. Field block `caption` dan catatan
  sumber slide dihapus oleh ADR 0017.

## Card metric dan quote

Card hanya dipakai dua block: `metric` dan `quote`. Tabel, chart, image,
diagram, divider, code, dan prosa tidak memakai card. Pola ini diturunkan dari
deck referensi 37 slide dengan 115 card:

- 16 dari 37 slide (43,2%) tidak memakai card sama sekali dan mediannya 2 card
  per slide. Nol card adalah tampilan normal, bukan kekurangan.
- Card hanya untuk himpunan item paralel pendek: 2–10 item, teks median 38
  karakter dan maksimum 145 karakter.
- Radius 9,6 px di 115/115 card, padding 24 px, dan border tidak terlihat di
  112/115 card.
- Tabel 0/6, chart 0/2, dan halaman pembatas 0/5 memakai card.

Nilai AutoOffice:

| Token | Nilai | Catatan |
| --- | --- | --- |
| `card.fill` | `#E5E7EB` | Kontras 1,19:1 terhadap background `#FAFAFA`; `surface` tetap untuk zebra tabel |
| `card.padding_emu` | 228600 | 24 px per sisi |
| `card.radius_emu` | 91440 | 9,6 px |

Card tidak menggambar border dan tidak memakai shadow, jadi fill adalah
satu-satunya pembeda dari background. Teks diletakkan 24 px dari tepi card, dan
measure memakai padding yang sama supaya tinggi card tidak meleset. Code block
tetap memakai card `surface` dengan border `#E5E7EB`; itu keputusan terpisah
yang belum diseragamkan.

## Tabel, code, dan chart

- Tabel memakai lebar kolom berbasis isi: minimum 40 px, maksimum 40% lebar
  tabel, padding sel 9.6 px per sisi. Tidak ada grid vertikal internal; header
  punya rule atas dan bawah, body hanya garis bawah. Zebra `surface` dan
  `surface_alt` dipertahankan, dan kolom numerik rata kanan termasuk header.
- Code block menggambar kartu native: fill `surface`, border `border`, radius
  `radius.md`, padding 19.2 px, dan tanpa shadow. Teks code 12 pt; filename
  12.5 pt.
- Chart memakai title 14 pt bold dari `label_pt`, data label nilai aktif untuk
  `bar`, `line`, dan `donut`, serta gridline 1 pt di value axis.
- Tidak ada inset `card_padding` phantom pada text, bullets, atau table. Media
  dan teks mulai di grid kiri yang sama.
- Metric dan quote memakai card dengan padding 24 px; ukuran teks dan tinggi
  card diukur dengan padding yang sama. Code tetap memakai padding 19,2 px
  dengan card `surface` dan border `border`.
- Caption `image` dan `diagram` menempel pada bounds gambar hasil contain,
  bukan pada tepi slot.

## Kontras

Aturan WCAG yang dipakai:

- teks normal minimal 4.5:1;
- teks besar minimal 3:1;
- warna seri chart minimal 3:1 terhadap permukaan chart;
- status tidak boleh dibedakan hanya lewat warna, selalu ada label.

Contoh pemeriksaan:

```python
from autooffice.design import resolve_theme
from autooffice.design.contrast import contrast_ratio

theme = resolve_theme("indigo")
assert contrast_ratio(theme.colors.ink, theme.colors.background) >= 4.5
assert contrast_ratio(theme.colors.muted, theme.colors.background) >= 4.5
assert all(contrast_ratio(color, theme.colors.surface) >= 3.0 for color in theme.chart.series)
```

`relative_luminance` dan `contrast_ratio` menerima warna heksadesimal enam
digit atau tuple RGB. Nilai kontras dipakai test, bukan dihitung ulang oleh
renderer.

## Known gap

- `cover_title_pt` 43.5 pt belum dipakai geometri produksi. Tempat yang
  memegang konteks layout ada di `overflow.py`, di luar lane theme, dan belum
  meneruskan `layout_id`; build masih memakai `title_pt` 30 pt untuk judul
  cover.
- `shadow` masih wajib di kontrak dan diteruskan ke gaya PlantUML, tetapi belum
  menjadi efek bayangan shape PPTX. Renderer mematikan shadow pada shape.
- Palet chart belum diuji ulang untuk color vision deficiency; jarak luminance
  antar-seri masih sempit.

## Aturan implementasi

- Warna, ukuran font, margin, gutter, radius, shadow, dan tracking hanya hidup
  di data token; modul Python di `src/autooffice` tidak menyimpan nilai
  heksadesimal.
- Deck authoring tidak menulis warna heksadesimal atau ukuran font.
- Tidak ada gradient dekoratif selain cover yang ditentukan token.
- Tidak ada glow, glass, blur dekoratif, blob 3D, atau pola acak.
- Tidak ada aksen pada body, caption, footer, atau nomor halaman.
- Theme tidak menambah zona aksen atau mengubah geometri layout.

Bukti kontrak ada di `tests/design/test_themes.py`, `test_contrast.py`, dan
`test_design_fonts.py`. Tes font memeriksa aset Liberation Sans untuk
pengukuran, bukan font tertanam di PPTX.

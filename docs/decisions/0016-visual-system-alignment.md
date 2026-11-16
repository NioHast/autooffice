# ADR 0016: Penyelarasan Visual, Skala Tipografi, dan Komposisi Vertikal

- Status: diterima
- Tanggal: 2026-11-15
- Pemilik: integration owner
- Keputusan terkunci: L05, L06, L08, L15, L19
- Rujukan: `AUTO_OFFICE_PLAN.md` bagian 6, 11, 12, 18, dan 19.2;
  [ADR 0004](0004-layouts-and-rendering.md),
  [ADR 0007](0007-slot-span.md),
  [ADR 0008](0008-min-one-of.md),
  [ADR 0009](0009-explicit-custom-rows.md),
  [ADR 0012](0012-chart-kind-preset.md),
  [ADR 0013](0013-remove-pdf-arial.md);
  [kontrak layout](../contracts/layout-spec.md),
  [kontrak design token](../contracts/design-token.md); dan
  `dist/deck-visual-final/VERIFICATION.md`.

## Daftar Isi

- [Konteks](#konteks)
- [Keputusan](#keputusan)
- [Kebijakan card](#kebijakan-card)
- [Konsekuensi](#konsekuensi)
- [Alternatif yang ditolak](#alternatif-yang-ditolak)
- [Bukti](#bukti)
- [Status](#status)

## Konteks

Audit visual membandingkan deck acceptance 24 slide dengan baseline
`deck-audit` dan menemukan masalah sistemik, bukan masalah satu slide:

- Ada dua grid kiri: blok teks, tabel, metric, dan quote mulai di 115,2 px,
  sedangkan divider dan shape lain mulai di 96 px. Selisih 19,2 px berasal dari
  inset `card_padding` phantom yang dihitung layout tetapi tidak digambar
  renderer. Divider tampak 19,2 px lebih lebar daripada teks di atasnya.
- Caption komponen dirender 16,5 pt, sedangkan caption media dan source 10 pt.
  Tidak ada satu gaya caption yang dapat diprediksi author.
- Type scale hanya tiga ukuran peran teks, yaitu 10, 16,5, dan 30 pt; code
  memakai 10,5 pt di luar skala peran. Akibatnya `display`, `lead`, `metric`,
  `caption`, `label`, dan `kicker` tidak punya identitas ukuran sendiri.
- Tabel memakai padding sel 4,8 px dan membagi lebar kolom sama rata. Kolom
  pendek seperti "No" menjadi terlalu lebar, sedangkan kolom teks panjang
  terlalu sempit.
- Code block tidak punya kartu, sehingga tidak terpisah dari latar dan batas
  visualnya tidak jelas.
- Chart native tidak menampilkan data label; pembaca harus menebak nilai dari
  posisi batang atau garis. Gridline belum memakai lebar token.
- 21 dari 24 slide menyisakan slack bawah. Rata-rata `|top gap - bottom slack|`
  adalah 110,51 px, sehingga komposisi terasa berat di atas. Row hanya
  ditumpuk dari `content_top` tanpa distribusi vertikal.
- Setelah token tipografi baru, row chart 16:9 masih menyisakan sekitar
  926.307 EMU (97,25 px) pada build terukur. Klaim lama bahwa row chart sudah
  menghabiskan tinggi area konten tidak benar; tanpa caption media, slack
  natural mencapai sekitar 1,16 juta EMU.

Perubahan ini menyentuh kontrak `LayoutSpec`, nilai token tipografi, perilaku
renderer, dan komposisi preset. Karena itu perubahan memerlukan ADR baru dan
tidak boleh diselesaikan sebagai improvisasi implementasi.

## Keputusan

### 1. Satu grid kiri dan inset yang eksplisit

- Inset `card_padding` phantom dihapus dari text, table, metric, dan quote.
  Pengukuran dan render memakai lebar slot penuh; teks dan tabel mulai di grid
  kiri 96 px yang sama dengan divider, chart, dan shape lain.
- `spacing.card_padding_emu` hanya dipakai sebagai padding kartu code (19,2 px
  per sisi) dan hanging indent bullet.
- Caption media (`image`, `diagram`) dimulai di tepi kiri geometry media hasil
  contain/cover, bukan di tepi slot. Lebarnya sampai tepi kanan slot dan
  tingginya dihitung ulang agar total block tidak melewati kotak layout.

### 2. Skala tipografi ber-tier

Nilai token tipografi yang berlaku:

| Token | Nilai |
| --- | ---: |
| `typography.display_pt` | 44 |
| `typography.cover_title_pt` | 43.5 |
| `typography.title_pt` | 30 |
| `typography.lead_pt` | 18 |
| `typography.body_pt` | 16.5 |
| `typography.metric_pt` | 42 |
| `typography.caption_pt` | 12.5 |
| `typography.label_pt` | 14 |
| `typography.minimum_pt` | 10 |
| `typography.kicker_tracking_em` | 0.08 |
| `code.size_pt` | 12 |
| `code.filename_pt` | 12.5 |

- Role `display` memakai `display_pt`; `title` memakai `title_pt` (dan
  `cover_title_pt` bila konteks cover tersedia); `lead`, `metric`, `caption`,
  `label`, serta `kicker` memakai token masing-masing.
- Caption tunggal 12,5 pt bobot 400 warna `muted`. Gaya ini berlaku untuk
  caption media, tabel, chart, diagram, metric, dan source.
- Code memakai 12 pt dan filename 12,5 pt. Tidak ada label chart atau teks
  kecil di bawah `minimum_pt` 10 pt.

### 3. Perilaku renderer

- Metric default memakai `colors.ink`. Hanya status `success`, `warning`, dan
  `danger` yang memakai warna status; `neutral` dan nilai tak dikenal kembali
  ke `ink`.
- Tabel memakai padding sel 9,6 px (`spacing.md_emu`). Lebar kolom dihitung
  dari isi: lebar alami tiap kolom (teks terlebar + padding) dijepit ke minimum
  40 px dan maksimum 40% lebar tabel, lalu sisa lebar dibagi ke kolom yang
  belum mencapai maksimum. Tidak ada grid vertikal internal.
- Code menggambar kartu native dengan fill `surface`, border `border`, lebar
  garis `divider_emu`, radius `radius.md_emu`, dan shadow dimatikan. Filename
  dan teks code berada di atas kartu.
- Chart memakai title `label_pt` 14 pt tebal, data label nilai aktif untuk
  `bar`, `line`, dan `donut`, serta gridline hanya di value axis dengan lebar
  `divider_emu` (1 pt). Tick dan legend memakai `minimum_pt`.

### 4. Komposisi vertikal `LayoutSpec.vertical_align`

- `LayoutSpec` mendapat field `vertical_align: Literal["top", "center"]`
  dengan default `"top"`. Nilai lain ditolak saat `LayoutSpec` dibuat.
- `"top"` mempertahankan perilaku lama dan tetap menjadi default API untuk
  kompatibilitas. `"center"` menempelkan row header pembuka di atas lalu
  menggeser row konten berikutnya sebesar `slack // 2`, dengan
  `slack = content_bottom - batas bawah stack`. Bila seluruh row adalah header,
  seluruh stack yang ditengahkan. Bila `slack <= 0`, tidak ada pergeseran.
- Klasifikasi header dilakukan per slot: row adalah header bila minimal satu
  slot ber-role `display`, `kicker`, `label`, `lead`, atau `title`, dan seluruh
  slot lain hanya `caption` pendamping. Caption tidak menurunkan status header,
  sehingga row `author` + `role` tetap header saat slot caption opsional hadir.
  Row caption tunggal dan row `title` + `body` tetap konten.
- Seluruh 19 preset bawaan memakai `"center"`, termasuk `bars`, `line`, dan
  `donut`. Row chart memakai media 16:9 yang tidak memenuhi tinggi area
  konten; membiarkannya `"top"` memindahkan slack ke bawah dan memperbesar
  ketidakseimbangan.
- Layout `custom` tidak memakai `LayoutSpec` preset. `plan_deck` memakai
  `CUSTOM_VERTICAL_ALIGN = "center"`; pemanggil API langsung
  `plan_custom_slide` tetap default `"top"`.
- Teks custom tanpa `role` diklasifikasikan sebagai body, bukan header. Judul
  custom yang harus dipin wajib menulis `role: title`.
- Pergeseran hanya mengubah `top_emu`. Lebar, tinggi, ukuran media, aspect
  ratio, dan temuan overflow tidak berubah. Overflow dihitung sebelum
  pergeseran, dan offset maksimum setengah slack sehingga tidak menghasilkan
  overflow baru.

### 5. Dokumentasi dan migration note

- Kontrak layout, panduan authoring, dan halaman learn layout menjelaskan
  `vertical_align`, arti `center`, kebijakan custom, serta kewajiban
  `role: title` pada judul custom.
- Deck custom lama tanpa `role: title` tetap valid, tetapi judulnya bergerak
  bersama konten. Migrasi dilakukan dengan menambahkan `role: title` pada
  block judul; tidak ada perubahan schema wajib.

## Kebijakan card

Bagian ini adalah amandemen yang menetapkan kapan card dipakai dan bagaimana
geometrinya. Card adalah keputusan renderer, bukan field schema; `deck.yaml`
tidak berubah.

**Sumber pola.** Riset terukur atas deck referensi
`Pertemuan_11.2Evaluasi_Validasi_Desain_SI.pptx` (37 slide, kanvas
12192000 x 6858000 EMU, 607 shape, 115 card) menghasilkan aturan R1, R2, R3,
dan R9. Angka pendukung yang dipakai:

| Aturan | Angka pendukung |
| --- | --- |
| R1 card untuk himpunan item paralel pendek | 2–10 item; teks card median 38 karakter, maksimum 145 |
| R2 nol card itu normal | 16/37 slide (43,2%) tanpa card; median 2 card per slide; maksimum 10 |
| R3 padding 24 px, radius 9,6 px, border tak terlihat | radius 9,6 px di 115/115 card; border sama dengan fill di 112/115; padding kiri 24 px di 54/115 |
| R9 jangan card untuk tabel, chart, halaman pembatas, prosa | 0/6 tabel, 0/2 chart, 0/5 halaman pembatas; prosa 213–563 karakter tanpa card |

**Keputusan.**

- Card hanya dipakai block `metric` dan `quote`. Tabel, chart, image, diagram,
  divider, code, dan prosa tetap tanpa card.
- Fill memakai token baru `card.fill` = `#E5E7EB`, bukan `surface`. `surface`
  tetap `#FFFFFF` karena dipakai zebra tabel. Kontras `#E5E7EB` terhadap
  background `#FAFAFA` adalah **1,19:1**; dari empat kandidat yang diukur,
  hanya nilai itu yang lolos target minimal 1,10.

  | Kandidat | Kontras vs `#FAFAFA` |
  | --- | ---: |
  | `#F3F4F6` | 1,05:1 |
  | `#EEF2FF` | 1,07:1 |
  | `#F1F5F9` | 1,05:1 |
  | `#E5E7EB` | **1,19:1** |

- Padding card 24 px (`card.padding_emu` = 228600 EMU), radius 9,6 px
  (`card.radius_emu` = 91440 EMU). Border tidak digambar (`a:ln` berisi
  `a:noFill`) dan shadow dimatikan (`shape.shadow.inherit = False`). Tanpa
  border dan shadow, fill adalah satu-satunya pembeda card dari background.
- Card digambar di belakang teks: shape card dibuat lebih dulu, lalu value,
  label, atau attribution. Teks memakai inset 24 px di keempat sisi.
- Kedua theme memakai `card.fill` yang sama karena `colors.background` juga
  sama (`#FAFAFA`) di `indigo` dan `hitam`; tidak perlu override per theme.
- Code block tidak berubah: card code tetap fill `surface`, border `#E5E7EB`
  1,33 px, padding 19,2 px, dan tanpa shadow. Ini tidak konsisten dengan card
  metric/quote, tetapi dipertahankan sampai ada keputusan terpisah.
- Tidak ada field schema baru dan tidak ada enforcement "maksimum 10 card per
  slide". Dengan hanya metric dan quote, overuse secara struktural tidak
  mungkin; jumlah card mengikuti jumlah block, bukan mekanisme baru.
- Butir 1 keputusan sebelumnya tetap berlaku untuk text, bullets, dan table.
  Untuk metric dan quote, inset yang berlaku bukan `spacing.card_padding_emu`
  (19,2 px, sekarang hanya untuk code dan hanging indent bullet), melainkan
  `card.padding_emu` 24 px yang benar-benar digambar sebagai card.

**Paritas measure dan render.** Padding 24 px mengubah tinggi block. Karena itu
`measure._measure_metric_block` dan `measure._measure_quote_block` memakai lebar
dalam `width - 2 x card.padding_emu` dan menambahkan `2 x card.padding_emu` pada
tinggi. `textbox.render_metric_block` dan `render_quote_block` memakai
`box.inset(card.padding_emu)` yang sama. Test paritas mengunci tinggi card sama
dengan `measure_block` pada toleransi 0 EMU, termasuk teks yang membungkus ke
beberapa baris.

## Konsekuensi

- Semua slide bergeser: grid kiri menjadi 96 px, tinggi teks berubah karena
  skala tipografi baru, lebar tabel berubah, dan row konten bergeser ke tengah.
  Golden visual lama tidak lagi berlaku dan harus dibuat ulang. Golden visual
  belum diperbarui dalam perubahan ini; artefak render terakhir adalah
  `dist/deck-visual-final/VERIFICATION.md` sebelum centering chart.
- `cover_title_pt` 43,5 pt sudah tersedia dan ter-resolve, tetapi belum dipakai
  call site produksi karena measurement belum meneruskan konteks layout
  `cover`. Build masih memakai `title_pt` 30 pt untuk judul cover. Ini known
  gap, bukan klaim bahwa token sudah aktif.
- Token `shadow` belum menjadi efek PPTX. Kartu code dan shape lain mematikan
  shadow; `shadow.card` dan `shadow.overlay` baru dipakai sebagai data gaya
  PlantUML.
- Palet chart belum diuji ulang untuk color vision deficiency. Kontras label
  donat di atas slice gelap juga masih di bawah target dan dicatat sebagai
  risiko R2 di `VERIFICATION.md`.
- `vertical_align="center"` mengubah posisi vertikal, bukan urutan row atau
  geometri horizontal. Karena default `LayoutSpec` tetap `"top"`, pemanggil
  yang membutuhkan perilaku lama dapat memilih `"top"` secara eksplisit.
- Author custom harus membedakan judul dan body melalui `role`; perilaku ini
  didokumentasikan dan diuji agar tidak bergantung pada tebakan mesin.

## Alternatif yang ditolak

- **Mempertahankan inset `card_padding` phantom dan menyeragamkan semua blok
  ke 115,2 px.** Ditolak karena grid 96 px adalah grid kanvas dan divider yang
  sudah dipakai shape lain. Menyeragamkan ke 115,2 px akan menggeser seluruh
  konten keluar dari grid, mempersempit area konten, dan tetap menyembunyikan
  inset yang tidak digambar renderer.
- **Memakai `card_padding` untuk semua blok.** Ditolak karena padding 19,2 px
  per sisi memotong lebar efektif teks, tabel, metric, dan quote tanpa ada
  kartu yang digambar. Hanya code yang memiliki kartu dan membutuhkan padding
  itu.
- **Tidak menambah tier tipografi.** Ditolak karena satu ukuran caption tidak
  dapat mewakili caption 10 pt dan caption komponen 16,5 pt sekaligus, dan
  `display`, `lead`, `metric`, serta `label` kehilangan hierarki. Mempertahankan
  tiga ukuran akan memaksa renderer memilih ukuran yang salah untuk salah satu
  peran.
- **Mempertahankan `vertical_align="top"` untuk chart.** Ditolak karena chart
  media 16:9 hanya memakai sebagian budget row. Pada build terukur, slack
  bawah chart 926.307 EMU (97,25 px), bukan pembulatan; centering menurunkan
  slack menjadi 463.154 EMU (48,63 px) tanpa mengecilkan media.
- **Menengahkan per slot di dalam row campuran.** Ditolak karena akan memecah
  baseline dan tinggi row: `author` dan caption pada row yang sama dapat
  memiliki `top_emu` berbeda. Row tetap bergerak sebagai satu unit; yang
  diklasifikasi per slot adalah status header row.
- **Mewajibkan `role` pada semua block text custom.** Ditolak karena demo dan
  deck lama memuat text/bullets custom tanpa role, dan schema tidak mewajibkan
  role. Perubahan itu akan menjadi breaking schema baru di luar kebutuhan
  komposisi. Sebagai gantinya, role menentukan klasifikasi dan migration note
  menjelaskan `role: title`.

## Bukti

Angka render dari `dist/deck-visual-final/VERIFICATION.md`:

| Temuan | Baseline | Build baru |
| --- | --- | --- |
| Blok teks/tabel/chart/card off-grid | 133 dari 147 blok, spread 19,2 px | 0 off-grid; 139 blok delta 0; caption media mengikuti gambar |
| Divider vs title | delta L -19,2, W +38,4 px | delta 0 / 0 / 0 |
| Caption komponen | 16,5 pt pada 21 caption | 12,5 pt pada 21 caption |
| Type scale | 10 / 10,5 / 16,5 / 30 pt | 12 / 12,5 / 14 / 16,5 / 18 / 30 / 42 / 44 pt |
| Tabel | padding 4,8 px, kolom sama rata | padding 9,6 px, kolom proporsional; kolom "No" 99,25 px |
| Code card | tidak ada | ada kartu `#FFFFFF`, border `#E5E7EB` 1,33 px, radius 9,6 px |
| Chart data label | bar/line tanpa `dLbls`; donut `showVal=false` | dLbls 3/3 dan `showVal=true` |
| Metric | `#374151` | `#0B0B0F` (`ink`) |
| Slack bawah | mean 152,79 px; selisih absolut top gap vs bottom slack 110,51 px | mean 125,12 px; selisih absolut 28,19 px |
| Chart | row chart top, slack 97,25 px | row chart center, slack 48,63 px (layout plan; render belum diulang) |

Bukti geometri chart dari rencana layout pada demo deck:

- `s06` bars, `s07` line, `s08` donut: sebelum centering, batas bawah stack
  5.322.093 EMU dan slack 926.307 EMU (97,25 px); setelah centering, batas bawah
  5.785.246 EMU dan slack 463.154 EMU (48,63 px).
- Tinggi chart tetap 3.615.213 EMU dan lebar 6.007.100 EMU pada kedua
  konfigurasi; posisi atas chart bergeser 463.153 EMU. Tidak ada overflow.
- `tests/deck/layout/test_vertical_align.py` mengunci default top, pinning
  header, centering section, row campuran `author` + caption, custom tanpa
  role, dan geometri slack chart untuk ketiga preset.

Golden visual belum diperbarui. Angka di atas adalah bukti render terakhir
sebelum centering chart; verifikasi chart setelah perubahan ini dilakukan pada
`LayoutPlan` dan test, bukan pada PNG baru.

## Status

Diterima. Perubahan kontrak `LayoutSpec`, nilai token tipografi, perilaku
renderer, kebijakan header, atau kebijakan `vertical_align` preset setelah ini
memerlukan ADR baru. Golden visual dan render PNG harus diperbarui di lane
verifikasi visual sebelum klaim final.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)

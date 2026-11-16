# Kontrak Design Token

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 11 (11.1-11.6), 6, dan keputusan L15.
Pemilik kontrak: design owner.

## Daftar Isi

- [Tujuan](#tujuan)
- [Invarian](#invarian)
- [Bentuk theme](#bentuk-theme)
- [Nilai tipografi](#nilai-tipografi)
- [Spasi turunan](#spasi-turunan)
- [Card konten](#card-konten)
- [Perilaku renderer](#perilaku-renderer)
- [Known gap](#known-gap)
- [Contoh konstruksi](#contoh-konstruksi)
- [Pemetaan acceptance](#pemetaan-acceptance)

## Tujuan

Kontrak ini membekukan token desain sebagai satu-satunya sumber warna,
tipografi, jarak, radius, shadow, grid, dan chart untuk renderer deck. Token
adalah data package `autooffice.design`, bukan berkas kerja pengguna.

## Invarian

1. Token minimal mencakup warna, tipografi, slide, grid, spacing, radius,
   card konten, shadow, chart (`chartSeries`, grid, axis, legend, title), dan
   code.
2. Semua renderer membaca token yang sudah di-resolve. Renderer tidak boleh
   memuat hex, ukuran font, margin, gutter, radius, shadow, tracking, divider,
   atau line-height hardcoded.
3. Hanya ada dua theme produk:
   - `indigo`, mode light, default.
   - `hitam`, mode light dengan aksen hitam, bukan dark theme.
4. `hitam` memakai kanvas terang, aksen `#111827`, dan cover gradient
   `#111827` -> `#0B1220` -> `#000000`. Palet `malam` tidak dipakai.
5. Pergantian theme hanya mengubah nilai warna. Objek `Theme` yang sudah
   di-resolve tetap membawa tipografi, grid, spacing, radius, shadow, dan code.
6. `chartSeries` berisi tepat empat warna dan wajib lolos kontras minimal 3:1
   terhadap background chart:
   - `indigo`: `#4F46E5`, `#0F766E`, `#B45309`, `#BE123C`.
   - `hitam`: `#111827`, `#374151`, `#4B5563`, `#6B7280`.
7. Palet aksen dan cover tetap persis baseline desain deck. Hanya warna chart
   yang memakai turunan `chartSeries` untuk aksesibilitas.
8. Chart dibatasi empat slot warna: seri untuk `bar`/`line`, kategori untuk
   `donut`.
9. Tipografi deck memakai `Arial` weight 400, 600, 700, dan 800. Ukuran per
   peran: display 44 pt, cover title 43.5 pt, title 30 pt, lead 18 pt, body
   16.5 pt, metric 42 pt, caption 12.5 pt, label 14 pt, dan minimum 10 pt.
   Kicker memakai caption 12.5 pt dengan tracking 0.08 em. Mono memakai
   system mono stack `ui-monospace, 'Cascadia Mono', Consolas, monospace`
   dengan ukuran 12 pt dan filename 12.5 pt. Tidak ada font family lain di
   deck.
10. DOCX mempertahankan font format baseline DOCX dan tidak memakai font
    theme deck.
11. PPTX tidak menanam font. Aset Liberation Sans (Regular dan Bold) dibundel
    hanya untuk pengukuran; family tampilan tetap Arial. Di Android/Linux tanpa
    Arial, aplikasi dapat mengganti Arial dengan Liberation Sans atau font
    substitusi lain.
12. Kontras teks normal minimal 4.5:1, teks besar minimal 3:1. Status tidak
    boleh menjadi satu-satunya pembeda; selalu ada label.
13. Dilarang gradient dekoratif selain cover, glow, glass, blur, blob 3D,
    pola acak, aksen pada body/caption/footer/page number, hex atau ukuran
    font di YAML, dan font di luar design system.
14. F0 membekukan bentuk, sumber, dan aturan token, bukan nilai akhir. Nilai
    final dibekukan setelah audit kontras pada F1-DESIGN; perubahan nilai
    memerlukan ADR dan pembaruan golden visual.

**Amandemen.** Nilai token tipografi, caption, dan perilaku visual pada
kontrak ini berubah melalui
[ADR 0016: Penyelarasan Visual, Skala Tipografi, dan Komposisi Vertikal](../decisions/0016-visual-system-alignment.md).
Golden visual belum diperbarui; pembaruan golden menyusul.

## Bentuk theme

F0 membekukan bentuk dan aturan token, bukan nilai akhir. Nilai final
dibekukan setelah audit kontras pada F1-DESIGN. Theme terdiri dari sub-dataclass
immutable `ThemeColors`, `ChartPalette`, `Typography`, `GridTokens`,
`SpacingTokens`, `RadiusTokens`, `ShadowTokens`, dan `CodeTokens`.

```python
Theme(name: str, mode: Literal["light"], colors: ThemeColors,
      chart: ChartPalette, typography: Typography, grid: GridTokens,
      spacing: SpacingTokens, radius: RadiusTokens, card: CardTokens,
      shadow: ShadowTokens, code: CodeTokens)
ThemeColors(background, surface, surface_alt, ink, ink_secondary, muted,
            border, accent, accent_deep, accent_soft, accent_line, accent_ink,
            status: Mapping[str, str])
ChartPalette(series: tuple[str, str, str, str], grid, axis, legend, title)
Typography(family, weights: tuple[int, int, int, int], display_pt,
           cover_title_pt, title_pt, lead_pt, body_pt, metric_pt,
           caption_pt, label_pt, minimum_pt, line_height, tracking_em,
           kicker_tracking_em)
GridTokens(columns, gutter_emu, margin_left_emu, margin_right_emu,
           margin_top_emu, margin_bottom_emu, row_gap_emu,
           slide_width_emu, slide_height_emu)
SpacingTokens(sm_emu, md_emu, lg_emu, card_padding_emu, divider_emu)
RadiusTokens(sm_emu, md_emu, lg_emu)
CardTokens(fill, padding_emu, radius_emu)
ShadowTokens(card, overlay, none)
CodeTokens(family, size_pt, filename_pt, line_height)
```

Semua objek theme immutable dan `status` bersifat read-only. Field `emu`
memakai integer English Metric Units agar renderer tidak menulis angka baru.

Nilai warna lain, spacing, grid, dan tipografi bersumber dari
`design-system/tokens.json` dan `design-system/themes.json` baseline desain
deck, lalu diport ke `src/autooffice/design/data/` oleh F1-DESIGN.

## Nilai tipografi

Nilai aktif ada di `src/autooffice/design/data/tokens.yaml`. Semua ukuran
memakai poin; kolom px sumber adalah dokumentasi konversi baseline
(1 px = 0.75 pt).

| Token | Nilai | Sumber px | Pemakaian |
| --- | --- | --- | --- |
| `typography.display_pt` | 44 | — | Role `display`: angka pembuka dan display besar. |
| `typography.cover_title_pt` | 43.5 | 58 | Role `title` saat layout cover memberi konteks; belum dipakai geometri produksi (lihat [Known gap](#known-gap)). |
| `typography.title_pt` | 30 | 40 | Role `title` pada layout non-cover. |
| `typography.lead_pt` | 18 | 24 | Role `lead`. |
| `typography.body_pt` | 16.5 | 22 | Body, heading, attribution, bullets, dan isi tabel. |
| `typography.metric_pt` | 42 | 56 | Value metric. |
| `typography.caption_pt` | 12.5 | — | Role `caption` dan `kicker`. |
| `typography.label_pt` | 14 | — | Label metric, title chart, dan author cover. |
| `typography.minimum_pt` | 10 | — | Lantai ukuran semua teks. |
| `typography.line_height` | 1.2 | — | Line-height teks non-code. |
| `typography.tracking_em` | -0.01 | — | Tracking teks non-kicker. |
| `typography.kicker_tracking_em` | 0.08 | — | Tracking role `kicker`. |

Pemetaan peran ada di `measure.role_typography`:

| Peran | Token ukuran | Bobot | Tracking |
| --- | --- | --- | --- |
| `display` | `display_pt` | `weights[3]` = 800 | `tracking_em` |
| `title` | `title_pt`, atau `cover_title_pt` bila konteks cover | `weights[2]` = 700 | `tracking_em` |
| `lead` | `lead_pt` | `weights[1]` = 600 | `tracking_em` |
| `body` | `body_pt` | `weights[0]` = 400 | `tracking_em` |
| `caption` | `caption_pt` | `weights[0]` = 400 | `tracking_em` |
| `label` | `label_pt` | `weights[1]` = 600 | `tracking_em` |
| `kicker` | `caption_pt` | `weights[2]` = 700 | `kicker_tracking_em` |

Value metric memakai `metric_pt` dengan `weights[3]`; label metric memakai
`label_pt` dengan `weights[1]`. Title chart memakai `label_pt` tebal. Code memakai
`code.size_pt` 12 pt dengan `weights[0]`, dan filename memakai
`code.filename_pt` 12.5 pt dengan `weights[1]`.

## Spasi turunan

Tidak setiap jarak punya kunci YAML sendiri. Nilai berikut diturunkan dari
token `spacing` oleh measure dan renderer; angka px memakai konversi grid
1 px = 9525 EMU.

| Pemakaian | Token sumber | EMU | px |
| --- | --- | --- | --- |
| Padding sel tabel per sisi (`table_cell_padding_emu`) | `spacing.md_emu` | 91440 | 9.6 |
| Hanging indent bullet | `spacing.card_padding_emu` | 182880 | 19.2 |
| Jarak antar-item bullet | `spacing.sm_emu` | 45720 | 4.8 |
| Padding kartu code per sisi | `spacing.card_padding_emu` | 182880 | 19.2 |

## Card konten

Card konten hanya dipakai block `metric` dan `quote`. Tabel, chart, image,
diagram, divider, code, dan prosa tidak memakai card. Card adalah keputusan
renderer, bukan field schema, dan tidak ada batas jumlah card per slide.

| Token | Nilai | Pemakaian |
| --- | --- | --- |
| `card.fill` | `#E5E7EB` | Fill card metric/quote |
| `card.padding_emu` | 228600 | Padding 24 px per sisi, dipakai measure dan render |
| `card.radius_emu` | 91440 | Radius 9,6 px |

`card.fill` terpisah dari `surface` karena `surface` `#FFFFFF` dipakai zebra
tabel. Kontras `#E5E7EB` terhadap `colors.background` `#FAFAFA` adalah 1,19:1,
satu-satunya kandidat yang lolos target minimal 1,10:

| Kandidat | Kontras vs `#FAFAFA` |
| --- | ---: |
| `#F3F4F6` | 1,05:1 |
| `#EEF2FF` | 1,07:1 |
| `#F1F5F9` | 1,05:1 |
| `#E5E7EB` | 1,19:1 |

Kedua theme memakai `card.fill` yang sama karena background kedua theme juga
`#FAFAFA`. Card tidak menggambar border (`a:ln` berisi `a:noFill`) dan tidak
memakai shadow.

## Perilaku renderer

**Bobot per peran.** `typography.weights` adalah satu-satunya sumber bobot.
Pemetaan peran terpusat di `measure.role_typography`; `textbox.role_style`
memanggil fungsi itu, dan `measure` memakai fungsi yang sama untuk mengukur.
`body_style` mengambil bobot body dari `weights[0]`, sehingga bullets dan
notes ikut token yang sama. Konstanta lama `_ROLE_WEIGHTS` dan default literal
`weight=400` di renderer sudah dihapus. Urutan tuple adalah 400, 600, 700, 800.

**Metric.** Value metric default memakai `colors.ink`. Hanya status `success`,
`warning`, dan `danger` yang memakai warna `colors.status`; `neutral` dan nilai
status tak dikenal kembali ke `ink`. Metric digambar di atas card `card.fill`
tanpa border dan tanpa shadow. Value dan label diberi inset `card.padding_emu`
24 px di keempat sisi.

**Quote.** Quote dan attribution juga digambar di atas card `card.fill` tanpa
border dan tanpa shadow, dengan inset `card.padding_emu` 24 px. Card dibuat
lebih dulu agar berada di belakang teks.

**Caption.** Hanya ada satu tier caption: `caption_pt` 12.5 pt, bobot 400,
warna `muted`. Gaya ini dipakai role `caption` pada block `text`, misalnya
keterangan kecil atau credit. Field block `caption` dan field slide `source`
dihapus oleh ADR 0017, sehingga renderer tidak membuat shape caption media.

**Tabel.** Lebar kolom dihitung dari isi: lebar alami tiap kolom (teks
terlebar plus padding) dijepit ke minimum 40 px dan maksimum 40% lebar tabel,
lalu sisa lebar dibagi ke kolom yang belum mencapai batas maksimum. Padding sel
9.6 px per sisi. Tabel tidak memakai grid vertikal internal: setiap sel hanya
punya garis bawah, header menambah garis atas, dan tidak ada `lnL`/`lnR`.
Zebra tetap dipertahankan dengan `surface` dan `surface_alt`. Header memakai
fill `accent` dan `accent_ink`; kolom emphasis memakai `accent_deep` pada header
dan `accent_soft` pada body. Kolom yang seluruh nilai body-nya numerik memakai
rata kanan, termasuk header-nya. Caption tabel dirender di bawah tabel.

**Code.** Code block menggambar kartu native sendiri: fill `colors.surface`,
garis `colors.border`, lebar garis `spacing.divider_emu`, radius `radius.md_emu`,
dan shadow dimatikan. Padding kartu 19.2 px per sisi. Filename memakai
`code.filename_pt` 12.5 pt, bobot 600, warna `ink_secondary`; teks code memakai
`code.size_pt` 12 pt.

**Inset.** Tidak ada inset `card_padding` phantom pada text, bullets, atau
table. Block tersebut memakai lebar slot penuh. Metric dan quote memakai inset
`card.padding_emu` 24 px karena card benar-benar digambar; measure memakai
lebar `slot - 2 x card.padding_emu` dan menambahkan `2 x card.padding_emu` pada
tinggi. Code tetap memakai `spacing.card_padding_emu` 19,2 px dengan card
`surface` dan border `border`.

**Chart.** Title chart memakai `label_pt` 14 pt dan bold. Data label nilai
aktif untuk `bar`, `line`, dan `donut` (`has_data_labels`, `show_value`).
Gridline hanya di value axis dengan lebar `divider_emu` 1 pt. Legend dan tick
label memakai `minimum_pt`.

## Known gap

Tiga hal berikut belum tertutup dan tidak boleh diasumsikan sudah selesai.

**`cover_title_pt` belum dipakai geometri produksi.** Token sudah ada dan
ter-resolve, dan `measure.role_typography(layout_id="cover")` mengembalikan
43.5 pt. Namun call site produksi, yaitu `measure._measure_text_block` dan
`textbox.render_text_block`, tidak meneruskan `layout_id`; satu-satunya tempat
yang memegang konteks layout adalah `overflow.py`, di luar lane theme, dan
tempat itu belum meneruskan `layout_id`. Build saat ini tetap memakai
`title_pt` 30 pt untuk judul cover.
Perbaikan memerlukan measurement yang sadar-layout agar ukuran render dan
ukuran ukur tidak berbeda.

**`shadow` belum menjadi efek PPTX.** Token `shadow` masih wajib di kontrak dan
diteruskan ke gaya PlantUML, tetapi tidak ada shape PPTX yang memakai
`shadow.card` atau `shadow.overlay` sebagai efek bayangan; renderer justru
mematikan shadow (`shape.shadow.inherit = False`). Kartu code sengaja tanpa
bayangan.

**Palet chart belum diuji ulang untuk CVD.** Empat warna seri lolos kontras
3:1 terhadap permukaan chart, tetapi palet belum diuji ulang untuk color vision
deficiency dan jarak luminance antar-seri masih sempit.

## Contoh konstruksi

```python
theme = Theme(
    name="hitam",
    mode="light",
    colors=ThemeColors(
        background="#FAFAFA",
        surface="#FFFFFF",
        surface_alt="#F9FAFB",
        ink="#0B0B0F",
        ink_secondary="#374151",
        muted="#6B7280",
        border="#E5E7EB",
        accent="#111827",
        accent_deep="#000000",
        accent_soft="#F3F4F6",
        accent_line="#D1D5DB",
        accent_ink="#FFFFFF",
        status={
            "neutral": "#374151",
            "success": "#0F766E",
            "warning": "#B45309",
            "danger": "#BE123C",
        },
    ),
    chart=ChartPalette(
        series=("#111827", "#374151", "#4B5563", "#6B7280"),
        grid="#E5E7EB",
        axis="#6B7280",
        legend="#374151",
        title="#0B0B0F",
    ),
    typography=Typography(
        family="Arial",
        weights=(400, 600, 700, 800),
        display_pt=44,
        cover_title_pt=43.5,
        title_pt=30,
        lead_pt=18,
        body_pt=16.5,
        metric_pt=42,
        caption_pt=12.5,
        label_pt=14,
        minimum_pt=10,
        line_height=1.2,
        tracking_em=-0.01,
        kicker_tracking_em=0.08,
    ),
    grid=GridTokens(
        columns=12,
        gutter_emu=91440,
        margin_left_emu=914400,
        margin_right_emu=914400,
        margin_top_emu=609600,
        margin_bottom_emu=609600,
        row_gap_emu=182880,
        slide_width_emu=12192000,
        slide_height_emu=6858000,
    ),
    spacing=SpacingTokens(
        sm_emu=45720,
        md_emu=91440,
        lg_emu=137160,
        card_padding_emu=182880,
        divider_emu=12700,
    ),
    radius=RadiusTokens(sm_emu=45720, md_emu=91440, lg_emu=182880),
    card=CardTokens(fill="#E5E7EB", padding_emu=228600, radius_emu=91440),
    shadow=ShadowTokens(
        card="0 1 2 0 rgba(17, 24, 39, 0.08)",
        overlay="0 8 24 0 rgba(17, 24, 39, 0.16)",
        none="none",
    ),
    code=CodeTokens(
        family="ui-monospace, 'Cascadia Mono', Consolas, monospace",
        size_pt=12,
        filename_pt=12.5,
        line_height=1.35,
    ),
)
assert theme.mode == "light"
assert theme.colors.accent == "#111827"
assert len(theme.chart.series) == 4
assert theme.grid.slide_width_emu == 12192000
```

Renderer menerima `theme` hasil resolusi; ia tidak membaca nama theme atau
nilai hex langsung. Resolver token (`resolve_theme`) adalah deliverable
F1-DESIGN; kontrak F0 hanya menetapkan bentuk, sumber nilai, dan aturan.

## Pemetaan acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Invarian | Bukti |
| --- | --- |
| Dua theme dan mode light | `tests/design/test_themes.py`; golden visual `hitam`. |
| `chartSeries` empat warna dan kontras 3:1 | `tests/design/test_contrast.py`. |
| Tidak ada hex di renderer | Contract test scan `deck/render/**`; review F1-DESIGN. |
| Font dan pengukuran | `tests/design/test_themes.py`; `tests/design/test_design_fonts.py`; `tests/deck/layout/`. |
| Tipografi dan ukuran minimum | Golden PPTX dan visual test; bagian 18.4. |
| Bobot per peran, tier caption, tabel, code card, dan chart | `tests/deck/layout/test_measure.py`; `tests/deck/render/pptx/test_textbox_edges.py`; `test_table.py`; `test_chart.py`. |
| Card metric/quote: fill, tanpa border/shadow, paritas measure-render 0 EMU | `tests/deck/render/pptx/test_card.py`; `tests/deck/layout/test_measure_edges.py`; `tests/design/test_contrast.py`. |
| Larangan desain | Contract test dan review golden; bagian 11.5. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)

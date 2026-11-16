# Kontrak Spesifikasi Block

Kontrak ini membekukan 11 block type yang boleh muncul di `deck.yaml`, field
wajib dan opsionalnya, serta aturan render native untuk table dan chart. Block
adalah unit konten terkecil; block tidak memiliki geometri, style inline, atau
teks yang diciptakan renderer.

Status: F0 contract, version 1; diamendemen [ADR 0017](../decisions/0017-remove-caption-and-source.md).
Sumber: AUTO_OFFICE_PLAN.md bagian 4.7, 4.8, dan 4.14.

## Bentuk data

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BlockSpec:
    block_type: str
    required: tuple[str, ...]
    optional: tuple[str, ...]
    key_leaves: tuple[str, ...]
    allowed_in_preset: bool


TABLE_SPEC = BlockSpec(
    block_type="table",
    required=("columns", "rows"),
    optional=("emphasis_column",),
    key_leaves=("hN", "rN.cM"),
    allowed_in_preset=True,
)

DIVIDER_SPEC = BlockSpec(
    block_type="divider",
    required=(),
    optional=(),
    key_leaves=(),
    allowed_in_preset=False,
)
```

`allowed_in_preset` hanya `false` untuk `divider` dan `spacer`; validator
menolak kedua tipe itu di layout preset. Sembilan tipe lain boleh dipakai di
preset.

## Daftar block

| Type | Wajib | Opsional | Key | Preset |
| --- | --- | --- | --- | --- |
| `text` | `text` | `heading`, `role` | `.text`, `.heading` | ya |
| `bullets` | `items` | `ordered` | `.itemN.text` | ya |
| `image` | `path`, `alt` | `fit` | tidak ada | ya |
| `table` | `columns`, `rows` | `emphasis_column` | `.hN`, `.rN.cM` | ya |
| `chart` | `kind`, `title`, `alt`, `categories`, `series` | `orientation`, `unit` | `.title`, `.catN`, `.seriesN.name`, `.seriesN.valueN` | ya |
| `code` | `code` | `language`, `filename`, `line_numbers` | `.code`, `.filename` | ya |
| `quote` | `text` | `attribution` | `.text`, `.attribution` | ya |
| `diagram` | `source`, `alt` | tidak ada | tidak ada | ya |
| `divider` | tidak ada | tidak ada | tidak ada | tidak |
| `spacer` | tidak ada | `size` | tidak ada | tidak |
| `metric` | `label`, `value` | `status` | `.label`, `.value` | ya |

Tidak ada block `callout`. Tipe di luar tabel ini ditolak validator. Field
`caption` pada `image`, `table`, `chart`, `diagram`, dan `metric` sudah
dihapus (ADR 0017) dan ditolak dengan pesan eksplisit.

## Aturan per tipe

- `text`: `heading` dan `text` adalah inline Markdown; `role` salah satu dari
  `display`, `title`, `lead`, `body`, `caption`, `label`, `kicker`.
- `bullets`: minimal satu item; setiap item satu paragraf inline Markdown;
  `ordered` boolean dengan default `false`.
- `image`: path relatif, format `.png`, `.jpg`, `.jpeg`, atau `.webp`; `alt`
  wajib non-kosong dan bukan key; `fit` hanya `contain` atau `cover`. Keterangan
  gambar ditulis sebagai block `text` terpisah dengan `role: caption`.
- `table`: jumlah sel setiap baris sama dengan jumlah kolom; tanpa merged cell,
  nested table, rowspan, atau colspan; `emphasis_column` 1-based dan hanya
  valid untuk layout `comparison`.
- `chart`: `bar`, `line`, atau `donut`; detail slot warna di
  [chart-contract.md](chart-contract.md).
- `code`: literal plain text, tidak diparse sebagai Markdown; nomor baris
  adalah chrome; code tidak boleh di-shrink.
- `quote`: `text` inline Markdown; `attribution` satu baris.
- `diagram`: `source` adalah path file `.puml`, dirender oleh PlantUML menjadi
  gambar; `source` di sini bukan catatan sumber slide.
- `divider`: ketebalan dan warna dari token, tanpa field teks.
- `spacer`: `size` hanya `sm`, `md`, atau `lg`; bukan tinggi absolut.
- `metric`: `status` hanya `neutral`, `success`, `warning`, atau `danger`.

## Invariant

- Tepat 11 block type; tidak ada tipe tambahan implisit.
- `id`, `type`, dan aturan `span` mengikuti [deck-schema.md](deck-schema.md).
- Block tidak memiliki `x`, `y`, `left`, `top`, `width`, `height`, `z`, atau
  `position`.
- Block tidak memiliki `font_size`, `color`, `margin`, `padding`, atau style inline.
- Field wajib tidak boleh kosong atau hanya spasi.
- `role` hanya ada pada `text`; pada preset nilainya harus sama dengan role slot.
- `image.alt` dan `diagram.alt` wajib non-kosong; `chart.alt` wajib non-kosong.
- Table wajib native di PPTX dan Google Slides, bukan gambar atau kumpulan shape.
- Table di PPTX memakai `shapes.add_table`; header adalah baris pertama.
- Chart wajib native di PPTX dan linked Sheets chart di Google Slides.
- Chart tidak boleh menjadi gambar.
- `divider` dan `spacer` tidak punya key, bukan konten teks, dan
  `allowed_in_preset` bernilai false.
- `notes` adalah field slide, bukan block. `source` pada block `diagram` adalah
  path file `.puml`; field slide `source` sudah dihapus (ADR 0017).
- Renderer tidak menciptakan teks, label, atau angka untuk block.

## Acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Aturan | Test kontrak |
| --- | --- |
| Block `callout` dan tipe asing ditolak. | `tests/contract/test_block_spec.py` (planned) |
| Field wajib hilang atau kosong ditolak per tipe. | `tests/contract/test_block_spec.py` (planned) |
| Field geometri dan style inline ditolak. | `tests/contract/test_block_spec.py` (planned) |
| `image.alt` kosong dan format SVG ditolak. | `tests/contract/test_block_spec.py` (planned) |
| Table dengan jumlah sel tidak konsisten ditolak. | `tests/contract/test_block_spec.py` (planned) |
| Chart dengan jumlah nilai tidak sama dengan kategori ditolak. | `tests/contract/test_block_spec.py` (planned) |
| Table native terdeteksi sebagai `table`, bukan gambar. | `tests/contract/test_block_spec.py` (planned) |
| Chart native terdeteksi sebagai chart part, bukan gambar. | `tests/contract/test_block_spec.py` (planned) |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)

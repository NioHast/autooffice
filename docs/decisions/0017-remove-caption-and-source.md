# ADR 0017: Hapus Caption Block dan Catatan Sumber Slide

- Status: diterima
- Tanggal: 2026-11-15
- Pemilik: integration owner
- Rujukan: ADR 0016, `docs/contracts/deck-schema.md`, `docs/contracts/block-spec.md`

## Konteks

Deck AutoOffice memiliki dua jalur teks yang tidak dipakai pengguna:

- field `caption` pada block `image`, `table`, `chart`, `diagram`, dan `metric`;
- field slide `source` berupa `text` dan `url` opsional.

Keduanya bukan sekadar data: caption menambah jalur ukur khusus media
(`media_caption_frame`), kotak render terpisah, key `media_text`, dan cabang
diagram/tabel/chart/metric. Catatan sumber slide menambah `SlideIR.source`,
key `source.text`, binding `kind: source`, aturan reserved block ID `source`,
dan shape renderer di margin bawah. Setiap jalur harus dijaga paritasnya
antara `measure` dan renderer, serta ikut coverage dan sinkronisasi teks.

Pengguna tidak memakai caption block maupun catatan sumber slide. Keterangan
kecil masih dibutuhkan, tetapi cukup sebagai block `text` biasa dengan
`role: caption`. Field `source` pada block `diagram` tetap dipertahankan karena
itu path file `.puml`, bukan catatan sumber.

## Keputusan

1. Hapus field `caption` dari schema, `BlockSpec`, compiler, bindings, coverage,
   measure, layout, dan renderer PPTX. Hapus `MediaCaptionFrame`,
   `media_caption_frame`, `media_caption_boxes`, `add_caption`, dan
   `caption_style`.
2. Hapus field slide `source` dari schema, `SlideDefinition`, `SlideIR`,
   `KeyKind`, key grammar, bindings, coverage, layout, renderer, Google
   extract/sync, dan copy checker.
3. Hapus `accepts_source` dari `LayoutSpec`; tidak ada lagi kotak sumber yang
   harus diakui layout.
4. Hapus reserved block ID `source`. Setelah catatan sumber slide hilang,
   `source` adalah block ID biasa.
5. Hapus seluruh data `source:` dan `caption:` pada `examples/demo-deck` serta
   fixture deck.
6. Field yang dihapus ditolak dengan pesan eksplisit yang menunjuk ADR ini,
   bukan hanya "field tidak dikenal".
7. `role: caption` pada block `text` dipertahankan. Tier tipografi
   `caption_pt` 12.5 pt tetap ada karena dipakai role tersebut, bukan karena
   caption media.

## Alternatif yang ditolak

- **Menjadikan `caption` dan `source` opsional lalu dibiarkan tidak dipakai.**
  Ditolak karena dua jalur ukur/render tetap harus diuji dan dijaga
  paritasnya, sehingga menambah biaya perawatan tanpa pemakai.
- **Mempertahankan caption hanya untuk tabel dan chart.** Ditolak karena
  caption tabel/chart memakai key, ukur, dan kotak render yang sama; memilih
  sebagian tipe hanya memindahkan kompleksitas, bukan menghapusnya.
- **Memakai `role: caption` pada block teks sebagai pengganti caption media.**
  Ini bukan alternatif yang ditolak: keputusan ini justru mempertahankan role
  tersebut sebagai satu-satunya cara menulis keterangan kecil.
- **Menghapus `source` pada block diagram.** Ditolak karena field itu adalah
  path file PlantUML, bukan catatan sumber slide.

## Konsekuensi

- Perubahan schema ini **breaking**. Deck lama dengan `source:` pada slide atau
  `caption:` pada block akan ditolak saat load/check/build dengan pesan field
  yang sudah dihapus dan rujukan ADR 0017.
- `SlideIR` kehilangan atribut `source`; `SlideDefinition` kehilangan atribut
  `source`; `LayoutSpec` kehilangan `accepts_source`.
- `KeyKind` hanya berisi `text`, `data`, dan `notes`. Key `sNN.source.text`
  tidak lagi dibuat, dan `media_text` tidak lagi dipakai.
- Coverage dan copy checker tidak lagi memeriksa teks sumber atau caption
  media. Alt text tetap wajib untuk `image`, `diagram`, dan `chart`.
- Renderer tidak lagi memendekkan chart/tabel/media untuk memberi ruang
  caption, dan tidak lagi menggambar shape di margin bawah.
- `role: caption` tetap valid untuk block `text`; tipografi 12.5 pt, warna
  `muted`, dan aturan header companion tidak berubah.

## Bukti

LOC diukur dengan `wc -l` pada working tree yang sudah memuat lane visual
belum commit. Angka "sebelum" untuk berkas inti diambil tepat sebelum
penghapusan dimulai; perubahan lane visual pada berkas yang sama ikut tercakup
di selisih.

| Berkas | Sebelum | Sesudah | Selisih |
| --- | ---: | ---: | ---: |
| `src/autooffice/deck/model/schema.py` | 1912 | 1811 | -101 |
| `src/autooffice/deck/model/deck_ir.py` | 128 | 116 | -12 |
| `src/autooffice/deck/model/keys.py` | 211 | 207 | -4 |
| `src/autooffice/deck/model/bindings.py` | 496 | 411 | -85 |
| `src/autooffice/deck/model/compiler.py` | 252 | 236 | -16 |
| `src/autooffice/deck/model/coverage.py` | 252 | 238 | -14 |
| `src/autooffice/deck/layout/measure.py` | 1228 | 1102 | -126 |
| `src/autooffice/deck/layout/custom.py` | 493 | 490 | -3 |
| `src/autooffice/deck/layout/slot.py` | 171 | 166 | -5 |
| `src/autooffice/deck/layout/spec.py` | 292 | 285 | -7 |
| `src/autooffice/deck/render/pptx/image.py` | 267 | 205 | -62 |
| `src/autooffice/deck/render/pptx/diagram.py` | 122 | 103 | -19 |
| `src/autooffice/deck/render/pptx/table.py` | 467 | 426 | -41 |
| `src/autooffice/deck/render/pptx/chart.py` | 221 | 132 | -89 |
| `src/autooffice/deck/render/pptx/textbox.py` | 784 | 720 | -64 |
| `src/autooffice/deck/render/pptx/renderer.py` | 328 | 319 | -9 |
| `src/autooffice/deck/copy/checker.py` | 514 | 501 | -13 |
| `examples/demo-deck/deck.yaml` | 748 | 691 | -57 |

Ringkasan:

- 18 berkas pada tabel di atas: 9.439 menjadi 8.712 baris (-727, termasuk 57 baris
  `deck.yaml`).
- Seluruh `src/autooffice/**` yang disentuh: 41 berkas, -707 baris.
- `tests/**` yang disentuh: 55 berkas (termasuk fixture dan conftest); 33
  fungsi test dihapus dan 5 test pengganti ditambahkan. Jumlah test lulus turun
  54, dari 3.583 menjadi 3.529. Baseline LOC test sebelum tugas tidak dapat
  diukur byte-exact karena working tree sudah memuat perubahan lane visual yang
  belum commit; seluruh `tests/**` sekarang 54.805 baris Python.
- Tidak ada berkas sumber yang dihapus seluruhnya; modul caption/source
  melekat pada berkas model, layout, dan renderer yang tetap ada.

Pemeriksaan regresi:

```bash
grep -rn "caption" src/autooffice/deck
grep -rn "SourceDefinition\|_validate_source\|_SOURCE_FIELDS" src/autooffice
grep -rn "media_caption" src/autooffice
```

Hasil yang diharapkan: hanya `role: caption` dan komentar ADR yang tersisa.

Verifikasi perilaku: `uv run pytest -q`, `ruff`, `mypy`, `lint-imports`,
`check_docs`, `check_tests`, build demo 24 slide, dan audit python-pptx untuk
shape caption/sumber serta shape di luar content area.

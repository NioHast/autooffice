# Indeks Architecture Decision Record

Status: F0 index, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 19.2 dan 13.2.

ADR mencatat keputusan yang mengikat kontrak. ADR yang sudah diterima tidak
diedit diam-diam; perubahan dilakukan dengan ADR baru yang menandai ADR lama
sebagai `superseded`. Perubahan schema, layout, block, atau perilaku renderer
setelah F0 wajib memiliki ADR.

## Daftar ADR

| ADR | Keputusan | Status |
| --- | --- | --- |
| [0001-assumption-closure.md](0001-assumption-closure.md) | Penutupan asumsi A1-A25 untuk kelulusan F0. | diterima; sebagian superseded oleh 0013 |
| [0002-scope-and-package.md](0002-scope-and-package.md) | Satu proyek, satu package Python, satu CLI, dan penghapusan repo lama. | diterima; target superseded oleh 0013 |
| [0003-deck-model-and-keys.md](0003-deck-model-and-keys.md) | Satu YAML per deck, ID stabil, flat key, dan 11 block type. | diterima |
| [0004-layouts-and-rendering.md](0004-layouts-and-rendering.md) | Katalog layout, grid, design token, PPTX native, dan font. | diterima; font/PDF superseded oleh 0013 |
| [0005-google-sheets-and-pdf.md](0005-google-sheets-and-pdf.md) | Linked Sheets chart, state Google, preflight table, dan PDF COM. | diterima; PDF/COM superseded oleh 0013 |
| [0006-quality-migration-and-humanizer.md](0006-quality-migration-and-humanizer.md) | Gate lokal, copy checker deterministik, transkrip, dan migrasi. | diterima; COM superseded oleh 0013 |
| [0007-slot-span.md](0007-slot-span.md) | Span per slot preset untuk layout asimetris, terpisah dari span custom. | diterima |
| [0008-min-one-of.md](0008-min-one-of.md) | Grup slot minimal satu untuk alternatif seperti toc group1-3 dan kpi kpi1-4. | diterima |
| [0009-explicit-custom-rows.md](0009-explicit-custom-rows.md) | Rows custom eksplisit di `SlideIR`; compiler mengisi, planner memakai. | diterima |
| [0010-risk-based-coverage.md](0010-risk-based-coverage.md) | Coverage global 90%, modul kritis 100%, adapter 85%; checker dan gate. | diterima; adapter PDF superseded oleh 0013 |
| [0011-f3-cleanup.md](0011-f3-cleanup.md) | Daftar hapus/update F3, inventaris referensi legacy, urutan operasi, dan rollback. | diterima; referensi PDF/COM superseded oleh 0013 |
| [0012-chart-kind-preset.md](0012-chart-kind-preset.md) | `SlotSpec.chart_kind` mengikat kind chart pada slot preset `bars`, `line`, dan `donut`. | diterima |
| [0013-remove-pdf-arial.md](0013-remove-pdf-arial.md) | Hapus PDF/COM/`pywin32`, field DOCX manual, Arial tanpa embedding, layout Liberation Sans. | diterima |
| [0014-plantuml.md](0014-plantuml.md) | PlantUML 1.2026.10, Java 21, Smetana, PNG, `-secure`, cache, dan sumber `.puml` menggantikan Mermaid. | diterima |
| [0015-native-heading-numbering.md](0015-native-heading-numbering.md) | Numbering heading native Word: `w:numPr` style + `numbering.xml`, override `numId=0`, caption tetap `SEQ`. Header `STYLEREF` dihapus lewat amandemen. | diterima |
| [0016-visual-system-alignment.md](0016-visual-system-alignment.md) | Satu grid kiri, skala tipografi ber-tier, caption 12,5 pt, tabel proporsional, code card, data label chart, dan `vertical_align` center untuk komposisi vertikal. | diterima |
| [0017-remove-caption-and-source.md](0017-remove-caption-and-source.md) | Hapus field block `caption` dan field slide `source` beserta jalur ukur, render, key, dan coverage-nya; `role: caption` pada block teks dipertahankan. | diterima |
| [0018-retire-styles-and-disable-highlighting.md](0018-retire-styles-and-disable-highlighting.md) | Pensiunkan 12 style reference, hapus palet syntax highlighting, pertahankan `Footnote*`, dan perkuat gate parity style. | diterima |
| [0019-reference-docx-as-single-visual-source.md](0019-reference-docx-as-single-visual-source.md) | `reference.docx` sebagai satu-satunya sumber kebenaran visual; edit reference langsung, backup biner pemilik, dan verifikasi minimal. Amandemen: front matter ditulis di `document.md`. | diterima |

## Aturan ADR

1. ADR wajib memuat konteks, keputusan, konsekuensi, alternatif, dan status.
2. ADR menyebut keputusan terkunci L01-L25 yang relevan.
3. ADR tidak menggantikan plan; plan tetap sumber keputusan produk.
4. Kontrak yang berubah wajib menautkan ADR yang mengubahnya.
5. ADR yang tidak lagi berlaku ditandai `superseded` dan menautkan pengganti.
6. ADR disimpan di `docs/decisions` dan terdaftar di halaman ini.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)

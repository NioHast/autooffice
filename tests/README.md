# Tes (`tests`)

## Tujuan

Folder ini memverifikasi perilaku `autooffice` pada beberapa tingkat: domain,
contract, CLI, Google, acceptance deck, packaging, performa, dan properti. Tes
menjadi bukti kontrak dan invariant output; fixture golden membekukan perilaku
DOCX. Jalankan pytest dari akar repo dengan `uv run --project . pytest`.

## Ownership

- [Testing](../docs/dev/testing.md) adalah acuan golden baseline dan cara
  menjalankan tes; [kontrak DOCX](../docs/contracts/docx.md) dan
  [kontrak test quality](../docs/contracts/test-quality.md) adalah acuan
  perilaku.
- `tests/_helpers/`, `tests/conftest.py`, dan fixture bersama dimiliki oleh
  pemilik infrastruktur tes. Tes domain dimiliki pemilik modul yang diuji.
- Perubahan `tests/fixtures/golden/` harus disertai alasan, pembaruan invariant
  JSON/hash, dan review; jangan mengubah baseline agar tes lulus.
- `pytest.ini` adalah sumber marker; jangan menambah marker tanpa
  mendaftarkannya.

## Pembagian folder

| Path | Isi dan kapan dipakai |
| --- | --- |
| `acceptance/` | Build PPTX demo deck nyata dengan font Arial tanpa embedding; marker `integration` dan `slow`. |
| `cli/` | Parser, target, output, doctor, build Markdown/deck, dan entry point. |
| `contract/` | Bentuk API dan scaffold kontrak. |
| `deck/` | Model, layout, chart, copy, transcript, renderer PPTX, dan Mermaid. |
| `design/` | Token, theme, Arial, Liberation Sans, dan kontras. |
| `docx/` | Pipeline DOCX, package, stage, terms, dan golden part. |
| `google/` | Auth, Drive, Sheets, Slides, state, dan fake contract. |
| `packaging/` | Metadata package, entry point `autooffice`, dan package data. |
| `performance/` | Deck besar dengan marker `slow`. |
| `property/` | Property test schema, key, layout, dan chart. |
| `tools/` | Checker quality dan mutation tooling. |
| `fixtures/` | Baseline golden, fixture DOCX, chart, copy, deck, dan reconcile. |
| `_helpers/` | Helper path dan utilitas bersama yang tidak bergantung cwd. |

## Tanpa Word, PowerPoint, dan COM

- DOCX dan PPTX dibangun sepenuhnya oleh pipeline Python. Tidak ada Word COM,
  PowerPoint COM, `pywin32`, atau konversi PDF.
- Field dan TOC Word tidak diperbarui otomatis; pengguna memperbaruinya manual
  di Microsoft Word setelah DOCX dibuka (Ctrl+A lalu F9).
- Word, PowerPoint, LibreOffice, dan aplikasi Office lain tidak boleh dipanggil
  dari tes. Jangan menambah marker atau skip yang bergantung pada aplikasi
  Office.
- Font PPTX ditulis sebagai family Arial dan tidak ditanam. Layout diukur
  dengan metrik Liberation Sans yang metrik-kompatibel Arial.

## Larangan

- Jangan menulis ke repo dari tes; gunakan `tmp_path` dan salin fixture.
- Jangan mengakses jaringan atau layanan eksternal.
- Jangan menghapus tes atau melemahkan assertion untuk membuat suite lulus.
- Jangan menambah skip karena fixture hilang; perbaiki fixture atau tes.
- Jangan memakai `python-docx` di kode runtime; di tes dan factory tetap boleh.
- Jangan menyimpan artefak build atau PDF hasil ekspor manual di
  `tests/fixtures/`.

## Tautan

- [Testing](../docs/dev/testing.md)
- [Kontrak DOCX](../docs/contracts/docx.md)
- [Kontrak test quality](../docs/contracts/test-quality.md)
- [Rencana refactor](../docs/dev/archive/refactor-plan.md)
- [Marker pytest](../pytest.ini)
- [README fixture reconcile](fixtures/reconcile/README.md)

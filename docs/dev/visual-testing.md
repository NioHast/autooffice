# Visual Testing PPTX

Status: harness visual dihapus bersama jalur COM/PDF. AutoOffice tidak lagi
mengekspor slide ke PNG lewat PowerPoint COM.

## Kondisi saat ini

- Harness visual dan semua path terkait sudah dihapus.
- Tidak ada `pywin32`, PowerPoint desktop, atau lock COM.
- `pytest.ini` hanya mendaftarkan marker `unit`, `integration`, `packaging`,
  dan `slow`.

## Verifikasi visual pengganti

Verifikasi visual dilakukan manual:

1. Build PPTX dengan `uv run autooffice build deck.yaml --target pptx`.
2. Buka PPTX di PowerPoint, Google Slides, atau LibreOffice.
3. Periksa layout, overflow, chart, tabel, dan gambar.
4. Bila perlu, ekspor PDF manual dan review hasilnya. Lihat
   [Ekspor PDF Manual](../user/pdf-export.md).

Verifikasi otomatis yang tersedia adalah invariant struktur PPTX di
`tests/deck/render/pptx/` dan golden part, bukan screenshot atau pixel diff.
Font PPTX adalah Arial tanpa embedding; di lingkungan tanpa Arial, aplikasi
dapat melakukan substitusi. Karena itu pixel diff lintas mesin tidak menjadi
target gate.

## Halaman terkait

- [Testing](testing.md)
- [Kontrak renderer PPTX](../contracts/pptx-renderer.md)
- [Design system](../learn/design-system.md)

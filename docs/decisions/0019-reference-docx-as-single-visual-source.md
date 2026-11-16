# ADR 0019: `reference.docx` sebagai Satu-Satunya Sumber Tampilan

- Status: diterima
- Tanggal: 2026-11-16
- Pemilik: DOCX owner
- Rujukan: [ADR 0015](0015-native-heading-numbering.md),
  [ADR 0018](0018-retire-styles-and-disable-highlighting.md),
  [kontrak DOCX](../contracts/docx.md),
  [style DOCX](../dev/docx/styles.md),
  [format dan struktur](../dev/formats.md), dan
  [roadmap penyederhanaan](../dev/roadmap-simplification.md)

## Konteks

Pipeline DOCX saat ini memakai dua artefak:

- **base `reference.docx`** di `src/autooffice/docx/data/formats/undip-msi/`
  yang menyimpan style dasar dan style yang tidak ditulis pipeline;
- **derived `reference.docx`** yang dibangun setiap build oleh stage
  `style_reference` dari `format.yaml`.

`format.yaml` menjadi sumber nilai visual untuk style dan geometri halaman.
Nilai numbering heading datang dari `structure.yaml`. Stage `style_reference`
menulis nilai itu ke derived reference. Base reference menyimpan style dasar
dan style yang sudah dibekukan, sedangkan style lain masih ditulis saat build.
Mengubah satu tampilan menuntut pemilik mengetahui apakah nilainya berasal dari
`format.yaml`, `structure.yaml`, atau dari base.

Fase 2a memindahkan lima style dari jalur generatif ke base:
`AbstractBody`, `AbstractKeywords`, `IstilahAsing`, `IstilahReview`, dan
`TableofFigures`. Untuk kelima style itu, `style_reference` sekarang hanya
memverifikasi keberadaannya, bukan menulis ulang definisinya. Perubahan ini
tidak mengubah output: hash C14N `word/styles.xml` sama dengan `main`, tiga
build berturut-turut menghasilkan sha256 yang sama, dan 36/36 heading+caption
tetap identik.

Pemilik memutuskan arah yang lebih tegas: `reference.docx` menjadi satu-satunya
sumber tampilan. Pemilik ingin mengedit reference langsung di Word atau melalui
agent, tanpa dua sumber yang harus dijaga bersamaan.

## Keputusan

1. **`reference.docx` adalah sumber kebenaran visual.** Style, numbering, dan
   geometri halaman ditentukan oleh isi reference, bukan oleh `format.yaml` atau
   `structure.yaml`.
2. **Perubahan visual dilakukan dengan mengedit `reference.docx`.** Perubahan
   style, numbering, atau geometri tidak lagi ditulis ke `format.yaml` lalu
   diregenerasi saat build.
3. **Pemilik menyimpan backup biner sendiri di luar repo.** File DOCX tidak
   dapat di-diff dan tidak dapat direview sebagai teks, sehingga backup menjadi
   pengaman utama saat reference rusak atau salah diedit.
4. **Verifikasi minimal yang dipertahankan, tidak lebih:**
   - setiap style wajib ada di reference dan build gagal bila style hilang;
   - setiap penanda `<!-- toc -->` menghasilkan field TOC;
   - front matter diakhiri section break.

   Verifikasi ini menjaga invariant yang tidak terlihat dari diff. Tidak ada
   verifikasi geometri per nilai, tidak ada perbandingan style per properti,
   dan tidak ada penulisan ulang style saat build.

## Alternatif yang ditolak

- **Tetap generatif dari `format.yaml` (status quo).** Ditolak karena pemilik
  ingin mengedit tampilan di Word atau melalui agent dan tidak ingin dua sumber
  untuk nilai yang sama. Setiap perubahan visual akan tetap menuntut edit YAML
  dan build ulang, sementara hasil edit langsung di reference akan tertimpa.
- **Hapus seluruh verifikasi.** Ditolak karena kegagalan akan menjadi diam.
  Mengubah `styleId` dan `w:name` sekaligus, misalnya, membuat `pStyle` menunjuk
  style yang tidak ada tanpa error saat build. Tanpa verifikasi, dokumen baru
  gagal atau tampil berbeda jauh setelah diedit di Word. Pembuktiannya ada di
  catatan audit style: referensi style yang menggantung tidak memunculkan
  exception, hanya style yang tidak terdefinisi di output.

## Konsekuensi

- **Derived reference dapat dihapus sepenuhnya.** Setelah seluruh style,
  numbering, dan geometri dibekukan, stage `style_reference` tidak lagi
  menghasilkan artefak yang berbeda dari base. Penghapusan stage itu menjadi
  fase tersendiri di roadmap (Fase 3d) dan diperkirakan mengurangi sekitar
  **3.000 LOC**.
- **`format.yaml` kehilangan alasan hidup.** Setelah nilai visual pindah ke
  reference dan front matter pindah ke `document.md`, `format.yaml` beserta
  `config/format.py` berpotensi dihapus pada Fase 3c.
- **Satu reference per kombinasi format × struktur.** Tesis, proposal, dan
  assignment memiliki front matter dan numbering yang berbeda, sehingga
  masing-masing membutuhkan reference sendiri. Tidak ada reference generatif
  yang menyatukan variasi itu saat build.
- **Biner tidak dapat direview lewat diff.** Perubahan visual tidak terlihat di
  pull request. Backup pemilik dan tiga verifikasi minimal menjadi pengaman
  yang menggantikan review baris per baris.
- **Perubahan visual memerlukan disiplin baru.** Setiap edit reference harus
  disertai backup dan pemeriksaan manual di Word; kesalahan yang lolos dari
  verifikasi minimal hanya terlihat pada dokumen hasil build.

## Bukti

- Fase 2a membekukan lima style di base reference pada `7a6f144` dan merge
  `6fd575e`. Jumlah style base naik dari 51 menjadi 56.
- Output final identik dengan `main`: hash C14N `word/styles.xml` sama, tiga
  build berturut-turut menghasilkan sha256 yang sama, dan 36/36 heading+caption
  identik.
- `style_reference` memverifikasi `BAKED_STYLE_IDS` dan tidak menulis ulang
  kelima style itu; perubahan perilaku tercakup oleh
  `tests/docx/test_style_reference.py`, `tests/docx/test_toc.py`, dan
  `tests/docx/test_lists.py`.

## Status

Diterima. Menghidupkan kembali derived reference generatif, menjadikan
`format.yaml` sebagai sumber nilai visual, atau menghapus verifikasi minimal
memerlukan ADR baru yang menandai ADR ini sebagai `superseded`.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)

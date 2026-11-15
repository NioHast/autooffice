# Aturan Agent

Halaman ini adalah checklist untuk agent yang mengubah AutoOffice. Setiap aturan
berasal dari kesalahan yang pernah terjadi dan dicatat di
[AUTO_OFFICE_EXECUTION_LOG.md](../../AUTO_OFFICE_EXECUTION_LOG.md). Ringkasan
invarian ada di [AGENTS.md](../../AGENTS.md); urutan langkah gate ada di
[quality-gates.md](quality-gates.md).

Aturan ini bukan pengganti gate. Sebelum commit, jalankan
`uv run python tools/quality/gate.py` dan pastikan seluruh langkah blocking lulus.

## Daftar isi

- [1. Jangan tinggalkan referensi ke fitur yang dihapus](#1-jangan-tinggalkan-referensi-ke-fitur-yang-dihapus)
- [2. Hapus kode mati setelah perubahan arsitektur](#2-hapus-kode-mati-setelah-perubahan-arsitektur)
- [3. Jangan percaya test hijau tanpa packaging atau wheel test](#3-jangan-percaya-test-hijau-tanpa-packaging-atau-wheel-test)
- [4. Cleanup harus sampai registry dan file, bukan hanya folder](#4-cleanup-harus-sampai-registry-dan-file-bukan-hanya-folder)
- [5. Jangan biarkan dokumen aktif menyebut perilaku lama](#5-jangan-biarkan-dokumen-aktif-menyebut-perilaku-lama)
- [6. Font dan aset harus punya hash dan divalidasi](#6-font-dan-aset-harus-punya-hash-dan-divalidasi)
- [7. Gate harus mendeteksi reintroduksi fitur yang dihapus](#7-gate-harus-mendeteksi-reintroduksi-fitur-yang-dihapus)
- [8. Jangan menambah dependency tanpa lock](#8-jangan-menambah-dependency-tanpa-lock)
- [9. Test harus menguji perilaku nyata, bukan mock yang selalu lulus](#9-test-harus-menguji-perilaku-nyata-bukan-mock-yang-selalu-lulus)
- [10. Jangan menulis nama fase, task, atau plan di kode dan dokumen aktif](#10-jangan-menulis-nama-fase-task-atau-plan-di-kode-dan-dokumen-aktif)
- [11. Jangan menambah fallback senyap untuk input wajib](#11-jangan-menambah-fallback-senyap-untuk-input-wajib)
- [12. Setiap perbaikan bug wajib punya test regresi](#12-setiap-perbaikan-bug-wajib-punya-test-regresi)
- [13. Verifikasi artefak final, bukan metadata build](#13-verifikasi-artefak-final-bukan-metadata-build)
- [14. Sinkronkan pengukuran layout dengan renderer](#14-sinkronkan-pengukuran-layout-dengan-renderer)
- [15. Validasi input tidak tepercaya dengan byte aktual](#15-validasi-input-tidak-tepercaya-dengan-byte-aktual)
- [16. Build gagal tidak boleh merusak sumber atau output lama](#16-build-gagal-tidak-boleh-merusak-sumber-atau-output-lama)
- [17. Jalankan gate penuh, bukan test subset](#17-jalankan-gate-penuh-bukan-test-subset)

## 1. Jangan tinggalkan referensi ke fitur yang dihapus

- **Aturan:** Hapus nama package, path, entry point, import, dan dokumentasi
  fitur yang sudah dihapus. Docs, CLI, dan test tidak boleh menyebut fitur itu
  seolah masih aktif.
- **Alasan:** Setelah PDF/COM dihapus, docstring modul PDF masih menyebut
  adapter PowerShell; setelah rename package, 152 berkas package lama dan
  rujukan nama lama di docs serta test masih tersisa.
- **Ditegakkan oleh:** `tools/quality/check_removed_features.py` (langkah gate
  `removed-features`) dan `tools/quality/check_no_legacy.py` (langkah gate
  `no-legacy`), dengan test `tests/tools/test_removed_features.py` dan
  `tests/tools/test_no_legacy.py`.

## 2. Hapus kode mati setelah perubahan arsitektur

- **Aturan:** Setelah kontrak, entry point, atau pipeline berubah, hapus modul,
  helper, fallback, dan scaffolding yang tidak lagi dipanggil. Jangan
  mempertahankan shim agar test lama tetap lulus.
- **Alasan:** Nama preset lama, scaffolding lane, `CLI-LANE-*`, `tools/dev`, dan
  adapter PowerShell lama tetap hidup setelah arsitektur pengganti selesai;
  semuanya baru dihapus pada pembersihan lanjutan.
- **Ditegakkan oleh:** `tools/quality/check_no_legacy.py`,
  `tools/quality/check_removed_features.py`, dan
  `tests/packaging/test_autooffice_package.py::test_legacy_entry_point_and_package_are_removed`.

## 3. Jangan percaya test hijau tanpa packaging atau wheel test

- **Aturan:** Verifikasi entry point, package data, dan isi wheel secara
  terpisah dari test unit. Test unit yang hijau tidak membuktikan paket bisa
  dipasang atau dibangun.
- **Alasan:** Seluruh test unit bisa lulus sementara entry point, package data,
  dan isi wheel masih salah; verifikasi akhir memerlukan wheel 196 entri dengan
  0 entri package lama.
- **Ditegakkan oleh:** `tests/packaging/test_autooffice_package.py`,
  `tests/packaging/test_wheel_contents.py` (marker `slow`), dan `uv build` pada
  gate final.

## 4. Cleanup harus sampai registry dan file, bukan hanya folder

- **Aturan:** Hapus instalasi sampai ke registry, file font, cache, state, dan
  uninstaller. Hapus folder saja tidak cukup dan meninggalkan perilaku lama.
- **Alasan:** Penghapusan font membutuhkan 4 nilai registry HKCU, 4 TTF,
  `WM_FONTCHANGE`, dan enumerasi GDI 0 family; instalasi LibreOffice
  membutuhkan 2.037.820.221 byte dan 21.012 file plus registry, AppData, serta
  uninstaller.
- **Ditegakkan oleh:** bukti enumerasi di
  `AUTO_OFFICE_EXECUTION_LOG.md` dan
  `tools/quality/check_removed_features.py` untuk sisa direktori font,
  dependency, atau extra di repo.

## 5. Jangan biarkan dokumen aktif menyebut perilaku lama

- **Aturan:** Dokumentasi aktif hanya menjelaskan perilaku saat ini. Setelah
  fitur dihapus atau validasi ditambahkan, perbarui `docs/user/`,
  `docs/contracts/`, dan `docs/dev/` pada perubahan yang sama.
- **Alasan:** `docs/user/cli.md` dan kontrak masih menyebut target `pdf`/`all`
  setelah target itu dihapus, dan dokumentasi pengguna menyatakan validator
  chart kind belum ada setelah validator itu ditambahkan.
- **Ditegakkan oleh:** `tools/quality/check_docs.py` untuk tautan, TOC, dan
  indeks; `tools/quality/check_no_legacy.py` untuk nama path lama di teks;
  klaim perilaku diverifikasi saat review dan dicatat di
  `AUTO_OFFICE_EXECUTION_LOG.md`.

## 6. Font dan aset harus punya hash dan divalidasi

- **Aturan:** Setiap aset font wajib punya hash SHA-256 yang dicatat dan diuji.
  Validasi isi file, bukan hanya header atau signature pendek.
- **Alasan:** Validasi aset font pernah hanya membaca 4 byte header; cache
  diagram pernah hanya memvalidasi 8 byte signature lalu menyajikan PNG korup.
- **Ditegakkan oleh:**
  `tests/design/test_design_fonts.py::test_font_hash_matches_manifest`,
  `tests/design/test_design_fonts.py::test_sha256_detects_tampered_font_bytes`,
  `tests/deck/media/test_plantuml_security.py`, dan allowlist font di
  `tools/quality/check_removed_features.py`.

## 7. Gate harus mendeteksi reintroduksi fitur yang dihapus

- **Aturan:** Setiap fitur yang dihapus wajib punya langkah gate yang menolak
  import, path, dependency, extra, dan konfigurasi lamanya kembali.
- **Alasan:** Tanpa langkah khusus, import `pywin32`, dependency `pypdf`, extra
  `windows`, path `autooffice.pdf`, dan font Plus Jakarta Sans dapat kembali
  tanpa gate gagal.
- **Ditegakkan oleh:** `tools/quality/check_removed_features.py` (langkah gate
  `removed-features`) dan
  `tests/tools/test_removed_features.py::test_gate_wires_removed_features_after_no_legacy`.

## 8. Jangan menambah dependency tanpa lock

- **Aturan:** Setiap dependency baru harus masuk `pyproject.toml` dan
  `uv.lock` pada perubahan yang sama. Jangan mengedit lock manual.
- **Alasan:** `mutmut` gagal dipasang di Python 3.15 Windows karena PyYAML
  6.0.3 tidak punya wheel cp315; `cosmic-ray` dipilih dan `uv.lock` diperbarui.
- **Ditegakkan oleh:** langkah gate `lock` (`uv lock --check`) dan
  `tools/quality/check_removed_features.py` untuk dependency terlarang.

## 9. Test harus menguji perilaku nyata, bukan mock yang selalu lulus

- **Aturan:** Patch hanya di boundary eksternal. Utamakan fake yang menjaga
  perilaku nyata dan assertion pada output akhir, bukan koreografi panggilan
  internal.
- **Alasan:** Test keamanan ZIP pertama hanya memeriksa pesan error dan
  mempercayai `ZipInfo.file_size`; verifikasi kemudian menemukan bypass
  `file_size = 0`. Mutation run `title_case` menyisakan 22 survivor karena
  assertion lemah.
- **Ditegakkan oleh:** `tools/quality/check_tests.py` (langkah gate
  `test-quality`), `tests/docx/test_package_security.py`, dan
  `tools/mutation/cosmic-ray.toml`.

## 10. Jangan menulis nama fase, task, atau plan di kode dan dokumen aktif

- **Aturan:** Komentar, docstring, dan dokumen aktif hanya menjelaskan perilaku
  saat ini. Nama fase, task, plan, nomor milestone, dan penanda TODO/FIXME
  tidak boleh muncul.
- **Alasan:** Komentar dan docstring pernah menyebut tag fase, lane, kata
  legacy, dan TODO; checker baru dibuat dan dijadikan blocking setelah
  pelanggaran itu tersebar.
- **Ditegakkan oleh:** `tools/quality/check_source_style.py` (langkah gate
  `source-style`) dan `tools/quality/check_identifiers.py` (langkah gate
  `identifiers`), dengan test `tests/tools/test_source_style.py` dan
  `tests/tools/test_identifiers.py`.

## 11. Jangan menambah fallback senyap untuk input wajib

- **Aturan:** Input wajib yang hilang, kosong, atau tidak valid harus melempar
  error domain. Jangan menambah nilai default atau jalur alternatif tersembunyi
  agar build tetap jalan.
- **Alasan:** Registry layout kosong, slide custom tanpa `rows`, `ctx.output_dir`
  hilang, environment Pandoc invalid, dan sync Google tanpa hasil eksplisit
  sempat diterima sebagai sukses.
- **Ditegakkan oleh:** `tests/deck/layout/test_registry.py`,
  `tests/deck/layout/test_custom.py`, `tests/docx/test_docx_config.py`, dan
  `tests/google/test_text_sync.py`; setiap penghapusan fallback dicatat di
  `AUTO_OFFICE_EXECUTION_LOG.md`.

## 12. Setiap perbaikan bug wajib punya test regresi

- **Aturan:** Test perbaikan harus gagal bila perbaikan produksi dikembalikan.
  Buktikan dengan revert sementara, lalu pulihkan perbaikan.
- **Alasan:** Perbaikan renderer dan keamanan ZIP berulang kali menemukan
  regresi yang tidak tertangkap test lama; pengukuran tabel emphasis dan
  validasi byte ZIP baru benar setelah test regresi ditambahkan.
- **Ditegakkan oleh:** `tools/quality/check_tests.py`, konfigurasi mutation
  `tools/mutation/cosmic-ray.toml`, dan test regresi di
  `tests/deck/render/pptx/` serta `tests/docx/test_package_security.py`.

## 13. Verifikasi artefak final, bukan metadata build

- **Aturan:** Coverage, caption, tabel, chart, dan teks harus diverifikasi dari
  DOCX atau PPTX final. Metadata, notes, YAML, model internal, dan state
  renderer bukan bukti.
- **Alasan:** Caption chart dibuang tetapi tetap dihitung coverage lewat
  metadata; key yang hanya ada di metadata harus ditolak.
- **Ditegakkan oleh:** `tests/contract/test_coverage_visibility.py` dan suite
  kontrak di `tests/contract/`.

## 14. Sinkronkan pengukuran layout dengan renderer

- **Aturan:** Saat ukuran, margin, gutter, line-height, atau bobot font berubah
  di renderer, perbarui `measure.py`, test pengukuran, dan golden visual pada
  perubahan yang sama.
- **Alasan:** Pengukuran code tidak menghitung filename, gap, dan gutter nomor
  baris; pengukuran tabel tidak memakai bobot kolom emphasis; notes memakai
  `a:spcPct` sementara renderer lain memakai `a:spcPts`.
- **Ditegakkan oleh:** `tests/deck/layout/test_measure.py`,
  `tests/deck/render/pptx/test_table.py`, dan
  `tests/deck/render/pptx/test_textbox_edges.py`.

## 15. Validasi input tidak tepercaya dengan byte aktual

- **Aturan:** Batasi input tidak tepercaya berdasarkan byte yang benar-benar
  dibaca, bukan ukuran yang diklaim metadata. Baca lewat stream dengan batas
  per entry dan total.
- **Alasan:** `ZipInfo.file_size` dan `compress_size` dipercaya; central
  directory dengan `file_size = 0` melewati batas. Loader YAML memakai `stat()`
  lalu `read_bytes()` sehingga file dapat membesar di antara kedua operasi.
- **Ditegakkan oleh:** `tests/docx/test_package_security.py`
  (`test_read_zip_rejects_understated_file_size_bomb`,
  `test_read_zip_rejects_actual_compression_ratio`) dan
  `tests/deck/model/test_loader_limits.py::test_load_deck_reads_at_most_limit_plus_one`.

## 16. Build gagal tidak boleh merusak sumber atau output lama

- **Aturan:** Tulis ke temporary, verifikasi, lalu ganti dengan `os.replace`.
  Kegagalan harus mempertahankan sumber, output final lama, workspace, dan
  state pengguna.
- **Alasan:** Tahap update field pernah membuka dan menyimpan DOCX sumber
  langsung; cleanup ambigu pernah menghapus workspace dan temp; jalur PDF lama
  pernah menghapus DOCX final lama.
- **Ditegakkan oleh:** `tests/cli/test_build_markdown.py`,
  `tests/cli/test_deck_build_errors.py`, dan
  `tests/docx/test_pipeline_edges.py`; bukti perilaku ada di
  `AUTO_OFFICE_EXECUTION_LOG.md`.

## 17. Jalankan gate penuh, bukan test subset

- **Aturan:** Jangan menyimpulkan kesiapan dari test subset atau hasil lane.
  Jalankan gate penuh dari working tree bersih sebelum commit, merge, atau
  rilis.
- **Alasan:** Banyak laporan menegaskan hasil lane bukan klaim gate final penuh;
  gate penuh baru dijalankan setelah seluruh perubahan selesai dan menjadi
  dasar kelayakan rilis.
- **Ditegakkan oleh:** `tools/quality/gate.py` dan catatan verifikasi di
  `AUTO_OFFICE_EXECUTION_LOG.md`.

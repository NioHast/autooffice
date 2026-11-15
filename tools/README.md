# Alat pengembang (`tools`)

## Tujuan

Folder ini berisi alat Python untuk pengembang dan peninjau, bukan kode runtime
`autooffice`. Alat membaca repo atau DOCX hasil build, lalu mencetak temuan;
tidak ada yang diimpor oleh `src/autooffice`. `tools/quality/` adalah rumah
untuk gate dan checker.

## Ownership

- [Testing](../docs/dev/testing.md) menjelaskan cara menjalankan tes alat dan
  baseline; [code style](../docs/dev/code-style.md) mengatur gaya Python alat;
  [registry referensi](../docs/dev/references.md) adalah sumber URL resmi.
- Alat baru harus punya penggunaan jelas, exit code terdokumentasi, dan tes di
  `tests/tools/`. Perubahan pada alat tidak boleh mengubah perilaku runtime
  `autooffice`.
- `tools/quality/` dimiliki test infrastructure owner; `tools/mutation/`
  dimiliki pemilik modul terkait.

## Alat yang tersedia

| Alat | Fungsi |
| --- | --- |
| `quality/gate.py` | Gate lokal berurutan: format, lint, types, imports, tests, coverage policy, lock, docs, test quality, no-legacy, removed-features, Python style, identifiers, dan source-style. |
| `quality/check_docs.py` | Memeriksa tautan relatif di README/docs aktif, TOC, judul, code fence, keterjangkauan indeks, dan registry `docs/dev/references.md`. |
| `quality/check_tests.py` | Memindai AST fungsi `test_*` dan melaporkan assertion, sleep, network, dan penulisan path. |
| `quality/check_coverage.py` | Membaca `.coverage` hasil `pytest-cov` dan menerapkan kebijakan coverage berbasis risiko. |
| `quality/check_python.py` | Memeriksa future import, alias typing warisan, dan API stdlib deprecated. |
| `quality/check_no_legacy.py` | Memeriksa path, package, import, entry point, dan teknologi legacy; exit 1 bila ada pelanggaran aktif. |
| `quality/check_removed_features.py` | Memeriksa import, path, dependency, `.mmd`, aset font PJS, dan konfigurasi fitur PDF/COM/Mermaid yang dihapus. |
| `quality/check_identifiers.py` | Memeriksa identifier definisi dan referensi wajib bahasa Inggris. |
| `quality/check_source_style.py` | Memeriksa komentar dan docstring bebas bahasa rencana atau riwayat. |
| `mutation/cosmic-ray.toml` | Konfigurasi mutation testing manual untuk modul kritis. |

## Alat dev vs resource runtime

- `tools/` adalah alat pengembang: dijalankan manual atau di gate, tidak
  dipaketkan ke wheel, dan tidak dipanggil pipeline.
- Runtime tidak membaca `tools/`. DOCX dan PPTX dibangun oleh pipeline Python
  tanpa Office, COM, atau skrip PowerShell.
- Alat boleh memakai API `autooffice` sebagai klien, tetapi `src/autooffice`
  tidak boleh mengimpor `tools/`.

## Larangan

- Jangan menambah dependensi runtime ke `pyproject.toml` hanya untuk alat;
  gunakan dev dependency.
- Jangan mengakses jaringan atau mengubah file pengguna. Checker bersifat
  read-only terhadap repo dan artefak.
- Jangan menduplikasi aturan dari `references.md` atau kontrak di dalam skrip.
- Jangan menulis output generated ke repo; gunakan path eksplisit pengguna
  atau direktori sementara.
- Jangan membuat alat yang diam-diam menjadi jalur build kedua.

## Tautan

- [Testing](../docs/dev/testing.md)
- [Code style](../docs/dev/code-style.md)
- [Registry referensi](../docs/dev/references.md)
- [Quality gates](../docs/dev/quality-gates.md)
- [Rencana refactor](../docs/dev/archive/refactor-plan.md)
- [Gate](quality/gate.py)
- [Check docs](quality/check_docs.py)

# Error dan Exit Code

Halaman ini menjelaskan kegagalan pipeline dan pemetaan exit code. Kontrak
error dan exit code ada di [contracts/cli.md](../../contracts/cli.md).

Semua error pipeline melempar subclass `DocgenError` atau `AutoOfficeError`.
Stage yang melempar exception tak dikenal dibungkus `StageError` dengan nama
stage, path, dan cause.

## Exit code

| Exit | Arti |
| ---: | --- |
| 0 | Sukses atau `check` tanpa temuan |
| 1 | Error input, konfigurasi, stage, tool, output, Google, atau temuan check |
| 2 | Kesalahan pemakaian CLI, target tidak valid, atau kombinasi flag salah |
| 130 | Dibatalkan pengguna |

Modul rekonsiliasi Adeu internal memakai kode tambahan 3 dan 4 bila dipanggil
langsung, tetapi kode itu bukan bagian permukaan CLI AutoOffice v1.

## Error PlantUML

Kegagalan input, engine, atau render diagram memakai kode berprefix
`PLANTUML-`. Build berhenti tanpa menulis PNG parsial; pesan menyebut path
sumber dan tindakan yang diperlukan, misalnya memasang PlantUML 1.2026.10 atau
lebih baru dan Java 21 atau mengatur `AUTOOFFICE_PLANTUML`. Kode yang umum
muncul adalah `PLANTUML-INPUT`, `PLANTUML-SOURCE`, `PLANTUML-TOOL`,
`PLANTUML-JAVA`, `PLANTUML-VERSION`, `PLANTUML-RENDER`, dan
`PLANTUML-OUTPUT`. Daftar lengkap ada di
[kontrak PlantUML](../../contracts/plantuml.md).

## Halaman terkait

- [overview.md](overview.md) untuk alur eksekusi.
- [options.md](options.md) untuk target yang dapat gagal.
- [outputs.md](outputs.md) untuk kegagalan penulisan.
- [../adeu-integration.md](../adeu-integration.md) untuk status modul Adeu.

# Artefak dan Workspace

Halaman ini menjelaskan artefak antara, workspace build, dan cara output
ditulis. Kontrak CLI ada di [contracts/cli.md](../../contracts/cli.md).
Artefak pengguna ada di [outputs.md](outputs.md).

## Workspace DOCX

Workspace default adalah `.laporan-build/` di samping `document.md`. Isinya
antara lain `plantuml.md` hasil stage `plantuml` (artefak
`plantuml.markdown`), Markdown hasil `front_matter`, PNG PlantUML di
`gambar/plantuml-<hash>.png`, `reference.docx` turunan, dan DOCX intermediate.
Tanpa `--keep-intermediate`, workspace dihapus di blok `finally`, termasuk saat
build gagal.

Tidak ada target PDF, sehingga workspace tidak pernah dipakai untuk DOCX
intermediate khusus PDF. Dengan `--keep-intermediate`, workspace dan DOCX
intermediate dipertahankan untuk diperiksa.

Stage `plantuml` memakai engine dari `AUTOOFFICE_PLANTUML` (jar atau
executable) dan opsional `AUTOOFFICE_JAVA`. PlantUML 1.2026.10 atau lebih baru
dijalankan di Java 21 dengan `-pipe` (stdin/stdout), `-secure`,
`--pragma layout=smetana`, dpi 192, `--disable-metadata`, `--threads 1`,
`--stop-on-error`, dan `--no-error-image`. Tidak ada kebutuhan Node.js,
Chromium, atau Graphviz. Kontrak dan batas resource ada di
[kontrak PlantUML](../../contracts/plantuml.md).

## Workspace deck

Workspace deck default adalah `.autooffice-build/<stem>/` di samping
`deck.yaml`. Renderer menulis staging PPTX dan aset PlantUML di sana. Cache
PlantUML persisten berada di `.autooffice/cache/plantuml/`, sedangkan state dan
review berada di `.autooffice/state/` dan `.autooffice/review/`.

Dengan `--keep-intermediate`, staging `slides` dan PPTX intermediate
dipertahankan kecuali memang dipublikasikan sebagai output final.

## Penulisan atomic

Penulisan output memakai file sementara di direktori tujuan dan `os.replace`.
DOCX/PPTX intermediate hanya berada di workspace dan tidak pernah ditulis ke
direktori output sebagai deliverable. PDF adalah hasil ekspor manual dan tidak
ditulis oleh pipeline.

## Referensi resmi

Label registry yang dipakai halaman ini: `Pandoc manual`, `PlantUML command
line`, `PlantUML security`. URL resminya ada di
[registry referensi](../references.md).

## Halaman terkait

- [outputs.md](outputs.md) untuk daftar artefak pengguna.
- [options.md](options.md) untuk `--keep-intermediate`.
- [stages.md](stages.md) untuk stage yang memakai workspace.
- [../docx/package.md](../docx/package.md) untuk aturan byte part.

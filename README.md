# AutoOffice

AutoOffice adalah pipeline dokumen dan presentasi dari satu sumber teks:
**DOCX dari Markdown** dan **PPTX/Slides dari YAML**. Pipeline DOCX memakai
Pandoc lalu merapikan package Word; pipeline deck memakai DeckIR, layout grid
12 kolom, serta tabel dan chart native di PowerPoint dan Google Slides. Deck
dapat disinkronkan ke Google Slides. AutoOffice tidak membangun PDF: PDF
diekspor manual dari Word atau PowerPoint setelah review.

## Status proyek

Ini adalah proyek pribadi. Tidak ada distribusi resmi, tidak ada dukungan, dan
tidak ada jaminan kompatibilitas API maupun versi.

AutoOffice adalah CLI deterministik yang dapat dioperasikan oleh AI agent. Tool
ini tidak memanggil model bahasa, tidak membutuhkan agent untuk berjalan, dan
tidak bergantung pada layanan eksternal selain Google Slides yang bersifat
opsional.

Fitur sengaja spesifik untuk kebutuhan penulisan tertentu, termasuk format
UNDIP MSI dan deck internal. Silakan fork dan sesuaikan dengan kebutuhan
masing-masing. Karena proyek tidak memiliki jalur rilis resmi, perubahan besar
dari luar tidak dijamin akan diterima atau dipertahankan.

- Tidak dipublikasikan ke PyPI; instalasi dari source.
- Prasyarat: Python 3.15, `uv`, Pandoc, Java 21, dan PlantUML 1.2026.10 untuk diagram.
- Lisensi kode MIT; aset Liberation Sans memakai SIL OFL 1.1.
- Tag `vX.Y.Z` adalah penanda milestone internal, bukan janji SemVer.

## Prasyarat

Daftar ini hanya memuat kebutuhan langsung. Seluruh paket Python, baik langsung
maupun transitif, dipasang otomatis dari `uv.lock`; jangan memasang `lxml`,
`pillow`, `python-pptx`, atau `ruamel.yaml` secara manual.

### Runtime

| Kebutuhan | Wajib untuk | Catatan |
| --- | --- | --- |
| Python 3.15 | semua perintah | Dikelola `uv`; versi ada di `.python-version`. |
| `uv` | semua perintah | Menyinkronkan `.venv` dan menjalankan `uv run`. |
| Pandoc dengan `--citeproc` | DOCX dari Markdown | Versi 3.x disarankan; `doctor` memeriksa ketersediaannya. |
| Java 21 | dokumen atau deck dengan diagram PlantUML | Diperlukan untuk menjalankan `plantuml.jar`; `AUTOOFFICE_JAVA` opsional. |
| PlantUML 1.2026.10 | dokumen atau deck dengan diagram PlantUML | Unduh `plantuml.jar` atau executable `plantuml`; set `AUTOOFFICE_PLANTUML`. |
| Kredensial Google OAuth | hanya target `slides` | `GOOGLE_CLIENT_ID` dan `GOOGLE_CLIENT_SECRET`; lihat [docs/user/google-oauth.md](docs/user/google-oauth.md). |
| Microsoft Word atau PowerPoint | opsional, manual | Memperbarui field DOCX (Ctrl+A, F9) dan mengekspor PDF. |

- Build DOCX dan PPTX tidak memerlukan Office, COM, `pywin32`, atau PowerShell.
- Jaringan hanya diperlukan untuk target `slides`.
- `uv run autooffice doctor` memeriksa Python, workspace, Pandoc, PlantUML,
  aset font bundled, dan modul Google untuk target `slides`.

### Development

| Kebutuhan | Catatan |
| --- | --- |
| Semua prasyarat runtime | Test acceptance memakai Pandoc; diagram memakai PlantUML. |
| `uv sync --extra dev --extra google` | Memasang paket dev dan Google ke `.venv`. |
| Python 3.15 dan `uv` | Sama seperti runtime. |

Alat pengembangan langsung: `pytest`, `pytest-cov`, `mypy`, `ruff`,
`hypothesis`, `import-linter`, `cosmic-ray`, dan `python-docx` (hanya untuk
test). Tidak ada alat dev yang masuk wheel runtime.

### Yang tidak perlu dipasang manual

- Paket Python runtime: `lxml`, `pillow`, `python-pptx`, `ruamel.yaml`.
- Paket Python dev: seluruh isi extra `dev`.
- Dependency transitif, misalnya `typing-extensions`, `google-api-core`, atau `aiohttp`.

Semua dipasang otomatis dari `uv.lock`. Daftar lengkap dapat diperiksa dengan
`uv tree`.

## Quickstart

DOCX dari Markdown. Siapkan `document.md` dengan front matter:

```bash
uv run autooffice build document.md --target docx
```

DOCX memakai field native Word. AutoOffice tidak mengisi hasil field; buka
DOCX di Word, tekan Ctrl+A lalu F9, sebelum review atau ekspor PDF. Rincian
front matter ada di
[docs/user/document-format.md](docs/user/document-format.md), dan alur ekspor
PDF ada di [docs/user/pdf-export.md](docs/user/pdf-export.md).

Diagram ditulis sebagai fence `{.plantuml caption="..."}`. Build merender PNG
dengan Java 21 dan PlantUML 1.2026.10; rincian ada di
[docs/user/plantuml.md](docs/user/plantuml.md).

Deck dari YAML. Contoh demo sudah berisi 24 slide. Target `pptx` memakai
family Arial tanpa embedding font. Layout diukur dengan Liberation Sans yang
metrik-kompatibel Arial. Block `diagram` menunjuk berkas `.puml` di
`diagrams/`, misalnya `diagrams/01-flowchart.puml`; PlantUML merender PNG saat
build.

```bash
uv run autooffice check examples/demo-deck/deck.yaml
uv run autooffice build examples/demo-deck/deck.yaml --target pptx
```

Hasil ditulis ke `examples/demo-deck/out/`. Target `slides` memerlukan extra
`google` dan kredensial OAuth. Langkah lengkap ada di
[docs/user/quickstart.md](docs/user/quickstart.md).

## Peta repo

| Path | Isi |
| --- | --- |
| `src/autooffice/docx/` | Pipeline DOCX: loader, stage, API package, dan terms. |
| `src/autooffice/deck/` | Model DeckIR, compiler, layout, renderer PPTX, chart, copy, dan transcript. |
| `src/autooffice/design/` | Token, theme, font Arial, pengukuran Liberation Sans, dan kontras. |
| `src/autooffice/google/` | Sinkronisasi Sheets/Slides dan state Google. |
| `src/autooffice/cli/` | Entry point `autooffice`, target, check, doctor, dan output. |
| `examples/` | Contoh DOCX dan `demo-deck`. |
| `docs/` | Panduan pengguna, developer, learn, kontrak, dan ADR. |
| `tools/` | Quality gate dan checker. |

## Kualitas

```bash
uv run python tools/quality/gate.py
python tools/quality/check_docs.py
python tools/quality/check_python.py
```

`gate.py` menjalankan format, lint, type check, import contracts, test,
coverage, lock, docs, test quality, no-legacy, removed-features, Python style,
identifiers, dan source-style. Ketiga perintah di atas tidak memanggil Office,
COM, atau Google.

## Dokumentasi

- [docs/user/quickstart.md](docs/user/quickstart.md): alur DOCX dan deck.
- [docs/user/deck-authoring.md](docs/user/deck-authoring.md): authoring `deck.yaml`.
- [docs/user/plantuml.md](docs/user/plantuml.md): diagram PlantUML, Java 21, dan instalasi engine.
- [docs/user/pdf-export.md](docs/user/pdf-export.md): ekspor PDF manual dari Word/PowerPoint.
- [docs/user/google-oauth.md](docs/user/google-oauth.md): tutorial OAuth Google.
- [docs/dev/README.md](docs/dev/README.md): arsitektur, pipeline, testing, gate.
- [docs/learn/README.md](docs/learn/README.md): konsep DeckIR, layout, design system.
- [docs/contracts/README.md](docs/contracts/README.md): kontrak normatif F0.
- [docs/decisions/README.md](docs/decisions/README.md): ADR keputusan.
- [docs/README.md](docs/README.md): indeks seluruh dokumentasi.

## Lisensi

MIT. Sebagian kaidah prosa dalam panduan berasal dari proyek naskah-id (MIT,
Copyright (c) 2026 nothinx). Teks lisensi lengkap ada di [`LICENSE`](LICENSE).

# Kontrak PlantUML

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 4.8, 8.6, dan 18.7; penggantian mesin
diagram dicatat di [ADR 0014](../decisions/0014-plantuml.md).

Kontrak ini membekukan render diagram PlantUML untuk code fence DOCX dan block
`diagram` deck. Tidak ada implementasi PlantUML di Python. AutoOffice hanya
membangun argumen, menjalankan engine eksternal, memvalidasi PNG, dan menyimpan
hasilnya.

## Daftar Isi

- [Ruang lingkup](#ruang-lingkup)
- [API](#api)
- [Aturan sumber dan path](#aturan-sumber-dan-path)
- [Tool, environment, dan output](#tool-environment-dan-output)
- [Error code](#error-code)
- [Cache](#cache)
- [Keamanan proses](#keamanan-proses)
- [Integrasi DOCX](#integrasi-docx)
- [Integrasi deck](#integrasi-deck)
- [Acceptance](#acceptance)

## Ruang lingkup

- Satu renderer PlantUML dipakai oleh pipeline DOCX dan renderer deck.
- Sumber deck adalah satu berkas `.puml`; satu fence DOCX adalah satu diagram.
- Output selalu PNG. SVG, PDF, teks, dan gambar error PlantUML bukan output
  yang sah.
- PlantUML dijalankan lokal. Tidak ada server, jaringan, browser, Node.js,
  Chromium, atau Graphviz.
- Tidak ada fallback ke teks, shape, screenshot, atau gambar lama saat render
  gagal.

## API

```python
from pathlib import Path

from autooffice.design.theme import Theme


def render_plantuml(
    source: Path,
    out: Path,
    *,
    theme: Theme,
    cache_dir: Path,
) -> Path:
    ...


def resolve_plantuml_source(deck_root: Path, relative_path: str) -> Path:
    ...


def find_plantuml() -> Path | None:
    ...


def find_java() -> Path | None:
    ...


def plantuml_version(executable: Path) -> str:
    ...
```

- `render_plantuml` merender satu berkas `.puml` dan mengembalikan path `out`.
  `out` wajib berakhiran `.png`.
- `theme` menentukan warna background PlantUML dan masuk ke fingerprint cache.
- `cache_dir` dibuat bila belum ada.
- `resolve_plantuml_source` memvalidasi field `source` relatif terhadap root
  deck sebelum file diserahkan ke renderer.
- `find_plantuml` mencari `AUTOOFFICE_PLANTUML` lalu `plantuml` di `PATH`.
- `find_java` mencari `AUTOOFFICE_JAVA`, lalu `JAVA_HOME/bin/java`, lalu `java`
  di `PATH`.
- `plantuml_version` membaca versi engine dan menolak versi di bawah
  1.2026.10.
- Semua kegagalan render memakai `PlantUmlError` dengan atribut `code` berisi
  kode `PLANTUML-*`. Stage DOCX juga dapat melempar `StageError` atau
  `ToolMissingError` dengan kode `PLANTUML-*`.

## Aturan sumber dan path

- Satu block `diagram` deck merujuk tepat satu berkas `.puml`.
- Ekstensi selain `.puml` ditolak sebelum engine dijalankan.
- Path wajib relatif, memakai `/`, tanpa segmen kosong, `.`, atau `..`.
- URL remote, UNC path, path absolut, drive letter, dan backslash ditolak.
- Path hasil resolve wajib tetap berada di bawah root deck.
- File yang tidak ada ditolak sebagai error, bukan dianggap diagram kosong.
- Symlink yang keluar dari root deck ditolak oleh resolve path.
- Sumber `.puml` deck dibatasi 1.000.000 byte.
- Fence DOCX wajib memiliki `caption` tidak kosong, isi tidak kosong, dan fence
  penutup. Fence biasa tidak disentuh.
- Direktif yang membaca berkas atau URL, termasuk `!include`, ditolak oleh mode
  `-secure`.

## Tool, environment, dan output

| Variabel | Wajib | Arti |
| --- | --- | --- |
| `AUTOOFFICE_PLANTUML` | untuk diagram | Path ke `plantuml.jar` atau executable `plantuml`. |
| `AUTOOFFICE_JAVA` | opsional | Path ke executable `java` untuk menjalankan jar. |
| `JAVA_HOME` | opsional | Fallback lokasi Java bila `AUTOOFFICE_JAVA` kosong. |

- Bila `AUTOOFFICE_PLANTUML` tidak diisi, executable `plantuml` dicari di
  `PATH`.
- Bila engine berupa jar, perintah dasar adalah
  `java -Djava.awt.headless=true -jar <plantuml.jar>`.
- Versi acuan adalah PlantUML 1.2026.10 dengan Java 21. Renderer deck menolak
  versi PlantUML yang lebih lama dengan `PLANTUML-VERSION`.
- `doctor` melaporkan pemeriksaan bernama `plantuml` berisi path engine dan
  versinya bila terbaca. Pemeriksaan ini tidak menggagalkan `doctor`; build
  diagram yang gagal tetap gagal keras.

Perintah render efektif, untuk jar:

```text
java -Djava.awt.headless=true -jar plantuml.jar \
  --png --charset UTF-8 --disable-metadata --threads 1 \
  --stop-on-error --no-error-image \
  --pragma layout=smetana \
  --skinparam dpi=192 \
  --skinparam backgroundColor=<background-theme> \
  -secure -pipe
```

Untuk executable `plantuml`, prefix `java -Djava.awt.headless=true -jar
plantuml.jar` diganti path executable. Sumber dikirim ke stdin; PNG dibaca dari
stdout. Tidak ada `-o`, URL, atau path output yang diserahkan ke PlantUML.

- `--pragma layout=smetana` memaksa Smetana, port Graphviz ke Java. Graphviz
  eksternal tidak dipakai.
- `--skinparam dpi=192` membekukan kerapatan PNG.
- `-secure` membatasi akses berkas dan URL dari sumber.
- `--no-error-image` dan `--stop-on-error` mencegah PNG error PlantUML menjadi
  output.
- `--threads 1` membuat render deterministik dan mudah dihentikan.
- Background deck berasal dari `theme.colors.background`; DOCX memakai nama
  warna PlantUML `white`.

### Validasi PNG

PNG dianggap valid hanya bila lengkap:

- signature PNG di awal file;
- chunk `IHDR` pertama dengan panjang 13 dan parameter yang masuk akal;
- sedikitnya satu chunk `IDAT`;
- chunk `IEND` terakhir dengan panjang nol, tanpa data setelahnya;
- seluruh CRC chunk cocok, dan tidak ada chunk yang terpotong.

Cache hit memakai validasi yang sama. Entri cache yang tidak lengkap atau rusak
dihapus lalu dirender ulang; file rusak tidak pernah disalin ke output.

## Error code

Semua kode memakai prefix `PLANTUML-` kecuali kode generik `PLANTUML`.
Kegagalan menghentikan build dan tidak menulis PNG final.

| Kode | Sumber | Arti |
| --- | --- | --- |
| `PLANTUML` | bersama | Kegagalan umum tanpa klasifikasi khusus. |
| `PLANTUML-SOURCE` | deck | Path, ekstensi, ukuran, atau keberadaan sumber tidak sah. |
| `PLANTUML-INPUT` | DOCX | Caption, isi fence, atau susunan blok tidak sah. |
| `PLANTUML-TOOL` | deck | PlantUML tidak ditemukan. |
| `PLANTUML-JAVA` | bersama | Java tidak ditemukan atau gagal dijalankan untuk jar. |
| `PLANTUML-VERSION` | deck | Versi PlantUML tidak terbaca atau di bawah 1.2026.10. |
| `PLANTUML-EXEC` | DOCX | Proses PlantUML tidak dapat dijalankan. |
| `PLANTUML-RENDER` | deck | Proses PlantUML gagal atau output melewati batas. |
| `PLANTUML-FAILED` | DOCX | PlantUML keluar dengan kode error selain kode khusus. |
| `PLANTUML-SYNTAX` | DOCX | PlantUML melaporkan syntax error (exit code 200). |
| `PLANTUML-NO-DIAGRAM` | DOCX | Sumber tidak memuat diagram (exit code 50). |
| `PLANTUML-TIMEOUT` | bersama | Render atau probe versi melewati batas waktu. |
| `PLANTUML-OUTPUT` | bersama | PNG tidak dihasilkan, tidak lengkap, atau tidak valid. |
| `PLANTUML-CACHE` | deck | Cache tidak dapat dibaca, ditulis, atau disalin. |
| `PLANTUML-WORKSPACE` | DOCX | Stage tidak mendapat workspace. |
| `PLANTUML-NO-DOCUMENT` | DOCX | Stage tidak mendapat document pada konteks. |
| `PLANTUML-STAGE` | DOCX | Kegagalan internal stage yang tidak terklasifikasi. |

Stage DOCX dapat melempar `ToolMissingError` dengan kode `TOOL-MISSING` bila
PlantUML tidak ditemukan sebelum render dimulai. Kode itu tetap dianggap
kegagalan PlantUML dan pesannya menyebut `AUTOOFFICE_PLANTUML`.

## Cache

Cache deck berada di `cache/plantuml/` di bawah workspace renderer. Workspace
deck disalin dari dan ke `.autooffice/cache/plantuml/` agar bertahan antar
build. Nama file:

```text
plantuml-<sha256>.png
```

SHA-256 dihitung dari payload kanonik berisi:

- hash isi `.puml`;
- fingerprint theme deck;
- versi PlantUML;
- opsi render: `format=png`, `dpi=192`, `layout=smetana`, `background`, dan
  `secure=true`.

Setiap PNG cache memiliki sidecar `plantuml-<sha256>.json` berisi `format`,
`digest`, `source_sha256`, `theme`, `plantuml_version`, dan `options`. Sidecar
dipakai untuk lookup cache-first: bila engine tidak tersedia atau versinya tidak
terbaca, renderer mencari sidecar dengan sumber dan theme yang cocok,
memvalidasi PNG, lalu menyalin PNG valid tanpa memanggil PlantUML. Bila engine
tersedia, lookup memakai digest lengkap yang memuat versi, sehingga perubahan
versi menghasilkan render baru.

Cache diperiksa sebelum PlantUML diwajibkan. Perubahan isi sumber, theme, versi,
atau opsi render menghasilkan cache key baru. File cache yang rusak atau bukan
PNG lengkap dihapus dan dirender ulang.

Pipeline DOCX memakai cache workspace, bukan cache persisten deck. PNG ditulis
ke `.laporan-build/gambar/plantuml-<hash>.png`. Hash dihitung dari isi diagram
yang dinormalisasi dan `RenderOptions` (`dpi`, `background`), lalu dipotong
menjadi 12 karakter. PNG yang sudah ada dipakai ulang tanpa memanggil PlantUML.
Hash DOCX tidak memuat versi engine; versi baru tetap memakai PNG yang sudah
ada.

## Keamanan proses

- Sumber tidak tepercaya diperlakukan sebagai data, bukan argumen shell.
- Perintah dibangun dari daftar argumen tetap; tidak ada `shell=True`.
- Sumber dikirim lewat stdin dan PNG diterima lewat stdout (`-pipe`).
- `-secure` membatasi `!include` dan akses berkas atau URL dari diagram.
- Path deck dibatasi di bawah root deck dan diverifikasi setelah resolve.
- Batas resource:

| Resource | Deck | DOCX |
| --- | --- | --- |
| Ukuran sumber | 1.000.000 byte | Tidak ada batas khusus di stage. |
| Output PNG | 64 MiB | 32 MiB |
| Output teks proses | 64 KiB per stream | stderr dipotong 2.000 karakter pada pesan error |
| Render | 180 detik | 180 detik |
| Probe versi | 30 detik | Tidak dipanggil stage. |

- Renderer deck menjalankan proses dalam process group baru dan menghentikan
  seluruh pohon proses saat timeout. Windows memakai Job Object dengan fallback
  `%SystemRoot%\System32\taskkill.exe /T`; POSIX memakai `killpg`.
- Penyalinan PNG cache dan output deck memakai `tempfile.mkstemp`, `flush`,
  `fsync`, lalu `os.replace`.
- Stage DOCX menulis PNG hanya setelah output lolos batas ukuran dan validasi
  PNG.
- Timeout, exit code bukan nol, output kosong, output terlalu besar, atau PNG
  tidak valid menghasilkan error keras.

## Integrasi DOCX

- Stage bernama `plantuml`, urutan 20, berjalan setelah `validate` dan sebelum
  `style_reference`.
- Stage membaca body `document.md`, mengekstrak fence `{.plantuml ...}`,
  merender, lalu menulis Markdown hasil penggantian ke `plantuml.md` dan
  artifact `plantuml.markdown`.
- Fence diganti dengan `![caption](gambar/plantuml-<hash>.png)`.
- Caption wajib dan menjadi alt text, bukan nomor manual.
- Nomor `Gambar bab.n` diberikan stage caption DOCX, bukan stage PlantUML.
- Stage selalu menulis `plantuml.md`, termasuk untuk dokumen tanpa blok, agar
  `front_matter` memiliki sumber body eksplisit.
- Diagram identik dalam satu build hanya dirender sekali.
- `check` tidak merender PlantUML dan tidak memvalidasi isi fence. Validasi
  caption dan isi terjadi saat build pada stage `plantuml`.

## Integrasi deck

- Block `diagram` memiliki field wajib `source` dan `alt`; `caption` opsional.
- `source` menunjuk satu berkas `.puml`; PlantUML tidak ditulis inline di YAML.
- `check` memvalidasi schema, path, ekstensi, dan alt tanpa merender.
- Renderer memanggil PlantUML hanya saat menemukan block `diagram` yang belum
  memiliki cache valid.
- PNG ditempatkan sebagai picture native pada kotak `PlacedBlock` dengan mode
  contain dan rasio aspek dipertahankan.
- Alt manusia ditulis ke `descr`; namespace block
  `autooffice:diagram:<slide>.<block>` ditulis ke `name` dan `title`.
- Caption dirender sebagai text box berkey `<slide>.<block>.caption`.
- Coverage memeriksa alt manusia dan key caption. Kegagalan render atau
  coverage membatalkan artefak final.
- Diagram di Google Slides tetap berupa gambar, bukan node native.

## Acceptance

| Aturan | Test |
| --- | --- |
| Fake engine menulis PNG dan argumen Smetana, dpi 192, serta `-secure` benar. | `tests/deck/media/test_plantuml.py` |
| Hanya `.puml` yang diterima dan path keluar root ditolak. | `tests/deck/media/test_plantuml.py` |
| Cache hit tidak menjalankan render ulang. | `tests/deck/media/test_plantuml.py` |
| Cache valid dipakai meski engine tidak tersedia. | `tests/deck/media/test_plantuml.py` |
| Cache dengan 8 byte signature saja dihapus dan dirender ulang. | `tests/deck/media/test_plantuml_security.py` |
| PNG valid wajib memiliki `IHDR`/`IDAT`/`IEND` dan CRC benar. | `tests/deck/media/test_plantuml_security.py` |
| Symlink pada nama temp tidak diikuti. | `tests/deck/media/test_plantuml_security.py` |
| Timeout menghentikan proses anak PlantUML. | `tests/deck/media/test_plantuml_security.py` |
| Batas ukuran sumber, output, dan timeout menghasilkan error. | `tests/deck/media/test_plantuml_security.py` |
| Perubahan sumber, theme, versi, dan opsi mengganti cache key. | `tests/deck/media/test_plantuml.py` |
| Engine hilang, versi lama, atau gagal berarti error keras. | `tests/deck/media/test_plantuml.py` |
| `doctor` melaporkan pemeriksaan `plantuml`. | `tests/cli/test_doctor.py` |
| Fence DOCX wajib caption, dirender, dan diganti gambar. | `tests/docx/test_plantuml_docx.py` |
| Syntax error DOCX memakai `PLANTUML-SYNTAX` dan tidak menulis PNG. | `tests/docx/test_plantuml_docx.py` |
| Diagram masuk PPTX sebagai picture dengan alt dan caption. | `tests/deck/render/pptx/test_diagram.py` |
| Tidak ada fallback teks atau shape. | `tests/deck/render/pptx/test_diagram.py` |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)

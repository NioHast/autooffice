# ADR 0014: PlantUML sebagai Mesin Diagram

Status: diterima
Tanggal: 2026-11-15
Terkait: [0012](0012-chart-kind-preset.md), [0013](0013-remove-pdf-arial.md),
[kontrak PlantUML](../contracts/plantuml.md), [panduan PlantUML](../user/plantuml.md)

## Konteks

AutoOffice membutuhkan diagram untuk naskah DOCX dan deck. Mesin diagram
sebelumnya memakai Mermaid CLI. Rantai itu membutuhkan Node.js, paket npm, dan
Chromium headless. Beban instalasi dan permukaan dependency menjadi besar untuk
alat yang harus berjalan lokal dan deterministik di Windows, Linux, dan macOS.

Kebutuhan diagram proyek didominasi UML, activity, sequence, dan entity
relationship. PlantUML mencakup kebutuhan itu dengan satu engine Java. PlantUML
1.2026.10 adalah rilis stabil pada 2026-11-11 dan menyediakan layout Smetana,
port Graphviz ke Java, sehingga Graphviz eksternal tidak diperlukan.

Keputusan ini menggantikan mesin diagram Mermaid pada seluruh pipeline aktif.
Riwayat kontrak lama tetap ada di git dan dokumen historis, tetapi tidak lagi
menjadi perilaku yang didukung.

## Keputusan

- Engine diagram adalah PlantUML 1.2026.10 atau lebih baru dengan Java 21.
- Sumber deck hanya berkas `.puml`; block `diagram` memakai field `source`.
- Sumber DOCX berupa code fence `{.plantuml caption="..."}`.
- Output selalu PNG dengan dpi 192. Tidak ada SVG, PDF, atau gambar error
  sebagai output diagram.
- Layout selalu Smetana melalui `--pragma layout=smetana`. Graphviz, browser,
  Node.js, dan Chromium tidak dipakai.
- Render selalu memakai `-secure`, `--no-error-image`, `--stop-on-error`,
  `--threads 1`, dan `-pipe`. Sumber dikirim lewat stdin dan PNG diterima lewat
  stdout.
- Engine dicari dari `AUTOOFFICE_PLANTUML`. Bila nilainya jar, Java dicari dari
  `AUTOOFFICE_JAVA`, lalu `JAVA_HOME`, lalu `PATH`.
- Cache deck memakai SHA-256 dari isi sumber, theme, versi PlantUML, dan opsi
  render. Cache disimpan di `.autooffice/cache/plantuml/`.
- `doctor` melaporkan pemeriksaan `plantuml` berisi path dan versi engine.
- Path sumber wajib relatif dan berada di dalam root deck. `!include` dan akses
  berkas atau URL dari diagram ditolak oleh `-secure`.

## Konsekuensi

Positif:

- Tidak ada Node.js, npm, Chromium, browser headless, atau Graphviz yang perlu
  dipasang.
- Satu engine Java menangani UML, activity, sequence, dan entity relationship.
- Render lokal, tanpa server dan tanpa upload diagram.
- Dependency diagram jauh lebih kecil daripada Mermaid CLI.
- Cache berbasis versi dan opsi membuat output dapat direproduksi.

Negatif:

- Java 21 menjadi prasyarat baru. Mesin tanpa Java 21 tidak dapat merender
  diagram.
- `plantuml.jar` berukuran puluhan megabyte dan harus disediakan pengguna.
- GitHub tidak merender PlantUML secara native seperti Mermaid. Pratinjau
  memerlukan ekstensi, server lokal, atau hasil build AutoOffice.
- Sumber Mermaid yang sudah ada harus ditulis ulang ke sintaks PlantUML.
- Layout Smetana tidak identik dengan Graphviz. Sebagian fitur khusus Graphviz
  dapat tampil berbeda atau tidak didukung.
- Versi PlantUML ikut cache key, sehingga peningkatan versi menghasilkan render
  baru.

Netral:

- Diagram di Google Slides tetap berupa gambar, bukan node native.
- Nomor gambar DOCX tetap diberikan stage caption, bukan engine diagram.

## Alternatif yang ditolak

- **Mempertahankan Mermaid.** Ditolak karena membutuhkan Node.js, npm, dan
  Chromium, serta menambah rantai dependency yang sulit dipin dan diaudit.
- **D2.** Ditolak karena ekosistem dan dukungan UML/ERD tidak selengkap
  PlantUML, dan tetap menambah engine baru tanpa menyelesaikan kebutuhan Java
  yang sudah ada di lingkungan build.
- **TikZ.** Ditolak karena membutuhkan LaTeX dan menambah rantai toolchain
  besar. TikZ juga menghasilkan PDF atau SVG yang harus dikonversi lagi.
- **Layanan online.** Ditolak karena diagram harus dirender lokal, tidak boleh
  dikirim ke pihak ketiga, dan build tidak boleh bergantung pada jaringan.

## Status

Diterima. Kontrak normatif ada di
[kontrak PlantUML](../contracts/plantuml.md). Panduan penulisan ada di
[panduan PlantUML](../user/plantuml.md). Perubahan schema, block, atau perilaku
renderer setelah keputusan ini wajib memiliki ADR baru.

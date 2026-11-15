# 01 - Model Mental

Halaman ini membangun model mental sebelum pembaca menyentuh kode. Setelah
membacanya, pembaca bisa menjelaskan lapisan data, membedakan sumber dan
artefak, memahami satu load/satu save, serta menjelaskan batas antara Python,
Pandoc, dan Word.

## Tujuan halaman

Setelah halaman ini, pembaca bisa:

1. menempatkan suatu berkas atau nilai ke lapisan yang benar;
2. menjelaskan mengapa DOCX tidak boleh menjadi sumber kebenaran;
3. menjelaskan alur package DOCX dari Pandoc sampai save;
4. menjelaskan peran manual Word untuk field dan ekspor PDF;
5. mengenali error zero-fallback dan tidak menggantinya dengan tebakan.

## Prasyarat

- [00 - Mulai di Sini](00-start-here.md).
- Mengenal Markdown dan YAML dasar.
- Tidak perlu memahami lxml atau OOXML. Halaman
  [04 - Model DOCX](04-docx-model.md) membahas XML secara bertahap.

## Daftar isi

- [Empat lapisan](#empat-lapisan)
- [Sumber kebenaran dan artefak](#sumber-kebenaran-dan-artefak)
- [Alur data](#alur-data)
- [Satu load dan satu save](#satu-load-dan-satu-save)
- [Batas Python, Pandoc, dan Word](#batas-python-pandoc-dan-word)
- [Zero-fallback sebagai kontrak](#zero-fallback-sebagai-kontrak)
- [Contoh konkret dari repo](#contoh-konkret-dari-repo)
- [Latihan](#latihan)
- [Halaman berikutnya](#halaman-berikutnya)
- [Referensi dan kontrak](#referensi-dan-kontrak)

## Empat lapisan

Setiap perubahan harus masuk ke lapisan yang tepat. Jika tidak, akan muncul
dua sumber kebenaran.

| Lapisan | Pemilik data | Contoh konkret | Pertanyaan yang dijawab |
| --- | --- | --- | --- |
| Konten | `document.md` dan aset di sampingnya | `examples/thesis-single/document.md`, `references.bib`, `gambar/` | Apa yang ditulis? |
| Struktur | `structure.yaml` | `src/autooffice/docx/data/structures/thesis/structure.yaml` | Bagian apa yang muncul dan dalam urutan apa? |
| Format | `format.yaml` dan aset format | `src/autooffice/docx/data/formats/undip-msi/format.yaml` | Bagaimana tampilannya? |
| Pipeline | `src/autooffice/docx/` | `pipeline.py`, `stages/`, `package/` | Bagaimana data diubah menjadi artefak? |

Aturan praktis:

- Jangan menulis margin atau font di `document.md`.
- Jangan menulis urutan bab di `format.yaml`.
- Jangan menyalin nilai `format.yaml` ke stage. Stage menerima model `Format`
  yang sudah divalidasi.
- Jangan mengubah DOCX hasil build untuk memperbaiki naskah. Perbaiki
  `document.md`, lalu build ulang.

`document.md` adalah satu berkas. Struktur `body` berisi daftar bab logis,
bukan daftar path berkas. Tidak ada folder `chapters/` dan tidak ada
`metadata.yaml` terpisah.

## Sumber kebenaran dan artefak

Sumber kebenaran adalah `document.md` beserta aset yang dirujuknya. DOCX,
manifest, review istilah, dan workspace adalah artefak turunan. PDF adalah
hasil ekspor manual pengguna, bukan artefak build.

```text
Sumber                         Artefak
document.md                    <report_name>.docx
references.bib                 .laporan/manifest.json
gambar/                        .laporan/istilah-baru.txt
istilah.tsv                    .laporan-build/ (sementara)
```

Konsekuensi:

- Mengubah DOCX tidak mengubah naskah. Build berikutnya akan menimpa
  perubahan itu.
- Modul rekonsiliasi internal membantu melihat edit manual pada DOCX, tetapi
  keputusan tetap diterapkan ke `document.md`.
- Nama artefak ditentukan `report_name` yang wajib di front matter.
- Output tidak ditulis ke `build/` atau `review/`.

`report_name` tidak punya default. Nilai kosong, hanya whitespace, atau
mengandung karakter path yang tidak aman ditolak dengan `CFG-REQUIRED` atau
`CFG-TYPE`.

## Alur data

Pipeline dapat dibaca dalam tiga kelompok besar:

| Kelompok | Stage | Hasil |
| --- | --- | --- |
| Persiapan | `validate`, `mermaid`, `style_reference`, `front_matter`, `pandoc` | Markdown final dan package DOCX awal. |
| Mutasi package | `sections` sampai `lists` | DOCX di memori dengan section, caption, field, nomor halaman, dan daftar. |

Tidak ada stage Word atau PDF. Urutan lengkap 16 stage dibahas di
[03 - Tahap Pipeline](03-pipeline-stages.md). Untuk model mental, cukup ingat
bahwa setelah `pandoc`, semua stage bekerja pada satu `DocumentPackage` di
memori.

`style_reference` adalah pengecualian yang sah: ia memuat `reference.docx`
sumber dan menyimpan versi turunan di workspace. Tidak ada stage yang memanggil
Word atau menulis ulang package setelah save.

## Satu load dan satu save

Aturan ini menjaga determinisme dan mencegah stage saling menimpa file.

1. `pandoc` membuat DOCX di workspace dan memuatnya menjadi
   `DocumentPackage`.
2. `Pipeline` menyimpan objek package itu di `ctx.package`.
3. Semua stage setelah `pandoc` memutasi part di memori.
4. Hook Adeu menambahkan bookmark dan menyiapkan manifest di memori.
5. `Pipeline` memanggil `save` tepat satu kali ke path output.
6. Manifest ditulis setelah save.

Stage tidak boleh memanggil `DocumentPackage.load` atau
`DocumentPackage.save` untuk package target. Jika stage butuh membaca part,
gunakan `package.xml(...)`. Jika stage butuh mengubah part, gunakan
`package.set_xml(...)` atau helper yang sudah ada.

Aturan ini membuat perubahan dapat diuji: part yang tidak dideklarasikan
stage harus tetap byte-identik.

## Batas Python, Pandoc, dan Word

Pembagian tanggung jawab:

| Komponen | Tanggung jawab | Tidak bertanggung jawab |
| --- | --- | --- |
| Python | Validasi, orkestrasi, mutasi XML, field, caption, nomor halaman, manifest. | Menjalankan Word atau mengisi hasil field. |
| Pandoc | Mengubah Markdown yang sudah dimaterialisasi menjadi DOCX awal dan memproses sitasi. | Membuat TOC native atau caption final. |
| Word (manual) | Memperbarui field dan mengekspor PDF setelah pengguna membuka DOCX. | Menentukan isi naskah atau menjadi bagian build. |

AutoOffice tidak memanggil Word. Field TOC yang baru dibuat belum memiliki
entri cache, sehingga TOC bisa tampil kosong sampai dokumen dibuka di Word dan
field diperbarui. Pengguna memilih seluruh dokumen dengan Ctrl+A lalu menekan
F9, atau memakai References > Update Table. Word juga yang menghasilkan PDF
manual dari DOCX final, bukan dari Markdown. Alur lengkap ada di
[Ekspor PDF Manual](../../user/pdf-export.md).

## Zero-fallback sebagai kontrak

Zero-fallback berarti satu input menghasilkan satu output dan error yang
jelas. Beberapa contoh nyata di repo:

| Kasus | Sumber perilaku | Error |
| --- | --- | --- |
| `report_name` hilang | `metadata.py` | `CFG-REQUIRED` |
| Kunci YAML tidak dikenal | `document.py`, `config/` | `CFG-UNKNOWN-KEY` |
| Artifact Markdown hilang sebelum Pandoc | `stages/pandoc.py` | `PANDOC-INPUT` |
| Lebar konten tidak bisa dihitung | `docx/page.py` | `PAGE-WIDTH` |
| DOCX untuk rekonsiliasi internal tidak ada | `autooffice.docx.adeu.reconcile` | `RECONCILE-INPUT` |

Yang tidak boleh dilakukan:

- menambahkan nama output default;
- mencari berkas di beberapa lokasi lalu memakai yang pertama ditemukan;
- memakai angka lebar halaman cadangan;
- menangkap error lalu melanjutkan dengan warning jika output menjadi ambigu.

Error adalah bagian dari kontrak. Saat error muncul, baca path, key, dan kode,
lalu perbaiki input atau data. Jangan menambal stage agar error hilang.

## Contoh konkret dari repo

Lokasi output dihitung di `src/autooffice/docx/paths.py`:

```python
def output_directory(document_path: Path) -> Path:
    parent = document_path.parent
    if parent.parent.name == "examples":
        return parent / "out"
    return parent
```

Fungsi ini tidak membaca direktori kerja saat ini dan tidak mencoba beberapa
folder. Dokumen contoh selalu ke `out/`; dokumen pengguna selalu ke folder
dokumen.

Package disimpan satu kali di `Pipeline.run`:

```python
ctx.package.save(docx_path)
ctx.artifacts.put("docx", docx_path)
```

Setelah baris itu, pipeline selesai. Semua mutasi stage sebelumnya sudah
selesai dan tidak ada pass Word atau PDF.

Verifikasi model mental dengan perintah read-only:

```bash
uv run python -c "from autooffice.docx.pipeline import CANONICAL_ORDER; print(len(CANONICAL_ORDER)); print(', '.join(item.value for item in CANONICAL_ORDER))"
```

Hasil yang diharapkan adalah `16` dan daftar stage dari `validate` sampai
`lists`.

## Latihan

### 1. Tempatkan nilai ke lapisan yang benar

Tanpa mengubah berkas, tentukan lapisan untuk nilai berikut:

- margin atas 4 cm;
- judul bab `Pendahuluan`;
- `report_name: "Tugas"`;
- urutan `body` pada struktur thesis;
- field TOC dan `PAGE`.

Cara memeriksa: cocokkan dengan tabel empat lapisan. Margin ada di format,
judul bab ada di konten, `report_name` ada di konten, urutan `body` ada di
struktur, dan field TOC/PAGE ditulis pipeline ke DOCX.

### 2. Jalankan check dan hitung hasil

Jalankan:

```bash
uv run autooffice check examples/thesis-single/document.md
```

Cara memeriksa: exit code 0 dan output `[OK] check <path>: bersih`. Perintah
ini tidak memanggil Pandoc atau Office.

### 3. Uji zero-fallback pada salinan

Salin `examples/assignment-single` ke direktori sementara di luar repo, hapus
baris `report_name` dari `document.md` salinan, lalu jalankan:

```bash
uv run autooffice check <path-salinan>/document.md
```

Cara memeriksa: perintah harus berhenti dengan exit code 1 dan pesan yang
memuat `report_name` serta `CFG-REQUIRED`. Jika build tetap berjalan dengan
nama default, berarti ada fallback yang melanggar kontrak.

## Halaman berikutnya

Lanjut ke [02 - Build Pertama](02-first-build.md) untuk menghasilkan DOCX
pertama dan melihat lokasi output.

## Referensi dan kontrak

| Kebutuhan | Dokumen |
| --- | --- |
| Arsitektur dan invariant | [architecture.md](../architecture.md) |
| Model eksekusi pipeline | [pipeline/overview.md](../pipeline/overview.md) |
| Urutan dan guard stage | [pipeline/stages.md](../pipeline/stages.md) |
| Format dan struktur | [formats.md](../formats.md) |
| Kontrak DOCX | [contracts/docx.md](../../contracts/docx.md) |
| Kontrak CLI | [contracts/cli.md](../../contracts/cli.md) |
| Ekspor PDF manual | [pdf-export.md](../../user/pdf-export.md) |

### Referensi resmi

Label registry yang dipakai halaman ini: `Python 3.15 pathlib`, `Pandoc
manual`, dan `OOXML ECMA-376`. URL resminya ada di
[registry referensi](../references.md).

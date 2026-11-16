# ADR 0020: Pengaturan per Dokumen di Front Matter

- Status: diterima
- Tanggal: 2026-11-16
- Pemilik: DOCX owner
- Rujukan: [ADR 0015](0015-native-heading-numbering.md),
  [ADR 0019](0019-reference-docx-as-single-visual-source.md),
  [kontrak DOCX](../contracts/docx.md),
  [numbering DOCX](../dev/docx/numbering.md),
  [roadmap penyederhanaan](../dev/roadmap-simplification.md), dan
  [format dokumen pengguna](../user/document-format.md)

## Daftar isi

- [Konteks](#konteks)
- [Keputusan](#keputusan)
- [Nilai dan perilaku](#nilai-dan-perilaku)
- [Alternatif yang ditolak](#alternatif-yang-ditolak)
- [Konsekuensi](#konsekuensi)
- [Bukti](#bukti)
- [Status](#status)

## Konteks

Setelah rencana penyederhanaan selesai, pipeline DOCX hanya memiliki dua
sumber:

- **`reference.docx`** untuk tampilan: style, definisi numbering, geometri
  halaman, dan part header/footer;
- **`document.md`** untuk metadata dan isi.

`format.yaml` dan `structure.yaml` dihapus. Tidak ada lagi konfigurasi paket
yang membawa nilai perilaku dokumen, dan tidak ada stage yang membangkitkan
reference dari YAML saat build.

Pengguna tetap perlu menyesuaikan perilaku dokumen tanpa menyentuh kode sumber:
nomor halaman, gaya tabel, caption, dan numbering heading. Setting itu
diletakkan di blok front matter `document.md`, bukan di dalam `reference.docx`,
karena DOCX adalah arsip biner: tidak dapat di-diff, tidak dapat direview
sebagai teks, dan mengubahnya membutuhkan parser serta penulis DOCX khusus.
Front matter sudah dibaca pipeline, sudah menjadi bagian dari dokumen, dan
perubahannya terlihat di diff Git.

## Keputusan

Empat key eksplisit di front matter `document.md` mengatur perilaku dokumen:

```yaml
heading_numbering: thesis  # thesis | arabic | none
pagination: thesis        # thesis | footer | none
tables: scientific        # scientific | grid
captions: on              # on | off
```

1. **Tidak ada key `profile`.** Tidak ada tabel profil di kode sebagai sumber
   nilai. Pipeline membaca keempat nilai itu langsung dari front matter; tidak
   ada pemetaan nama profil ke sekumpulan nilai.
2. **`heading_numbering` hanya mengatur nomor heading** (`BAB I`, `1.`, atau
   tanpa nomor). **List numbering** (`1.`, `a.`, `i.`) selalu berasal dari
   Markdown dan tidak pernah dimatikan oleh setting ini.
3. **Nilai yang tidak ditulis jatuh ke perilaku `thesis`.** Dokumen lama dan
   contoh yang belum memiliki key tetap dapat dibuild dengan perilaku yang
   sama seperti sebelumnya.
4. **`autooffice scaffold` menulis keempat key secara eksplisit** pada dokumen
   baru. Pengguna baru melihat pilihan yang tersedia, bukan mewarisi default
   secara diam-diam.
5. **`reference.docx` tetap menyimpan style, definisi numbering, geometri
   halaman, dan part header/footer.** Dokumen memilih **apakah** part footer
   dipakai, bukan membuat part footer baru.

## Nilai dan perilaku

| Key | Nilai | Perilaku |
| --- | --- | --- |
| `heading_numbering` | `thesis` | Heading 1 `BAB I`, Heading 2 `1.1.`, Heading 3 `1.1.1.` |
| | `arabic` | Heading 1 `1.`, Heading 2 `1.1.`, Heading 3 `1.1.1.` |
| | `none` | Tanpa nomor heading. |
| `pagination` | `thesis` | Nomor halaman mengikuti konvensi tesis: romawi di front matter, arabik di body. |
| | `footer` | Nomor halaman di footer untuk seluruh dokumen tanpa konvensi front matter tesis. |
| | `none` | Tanpa nomor halaman. |
| `tables` | `scientific` | Border atas dan bawah 1 pt, garis bawah header, tanpa garis vertikal. |
| | `grid` | `TableGrid` penuh 0,5 pt. |
| `captions` | `on` | Caption tabel dan gambar ditulis. |
| | `off` | Caption tabel dan gambar tidak ditulis. |

Default keempat key bila tidak ditulis adalah `heading_numbering: thesis`,
`pagination: thesis`, `tables: scientific`, dan `captions: on`.

Pemisahan heading numbering dan list numbering bukan detail implementasi. Kedua
hal berasal dari mekanisme yang berbeda: heading memakai definisi numbering pada
`reference.docx`, sedangkan list memakai numbering yang ditulis Pandoc dari
Markdown. Karena itu `heading_numbering: none` tidak boleh mematikan list
`1.`, `a.`, atau `i.` di body dokumen.

## Alternatif yang ditolak

| Alternatif | Alasan ditolak |
| --- | --- |
| Setting di dalam `reference.docx` (custom property) | DOCX adalah biner: tidak bisa di-diff, tidak bisa direview sebagai teks, dan membutuhkan parser serta penulis DOCX khusus. Solusi itu justru menambah kode yang ingin dihindari. |
| Key `profile:` dengan tabel profil di kode | Mengubah default untuk semua dokumen berarti menyunting kode. Pengguna memilih nol kode, sehingga nilai harus berada di dokumen. |
| Setting global di satu file `.yaml` | Menambah file konfigurasi yang justru sedang dihapus oleh rencana penyederhanaan. |
| Semua key wajib (tanpa default) | Dokumen lama dan contoh yang belum memiliki key akan gagal build. |

## Konsekuensi

- **Empat baris per dokumen.** `autooffice scaffold` mengisi keempat key secara
  otomatis pada dokumen baru; dokumen lama tetap build dengan default tesis.
- **Definisi numbering tetap milik `reference.docx`** karena numbering heading
  membutuhkan `word/numbering.xml`. Karena itu ada tiga reference: thesis
  (romawi), proposal (arabik bertitik), dan tugas (tanpa heading numbering).
  `heading_numbering` memilih varian reference yang membawa definisi numbering
  sesuai nilainya; dokumen tidak menulis ulang `numbering.xml`.
- **`native_numbering.py` tidak dihapus.** Bagian penulisan definisi numbering
  dihapus, tetapi verifikasi dan override `numId=0` per paragraf tetap ada.
- **Makalah dua kolom nanti menjadi reference keempat.** Gambar dan tabel
  selebar halaman belum didukung.
- **Tidak ada lagi cara mengubah tampilan lewat teks.** Key di front matter
  hanya mengatur perilaku; perubahan visual berarti mengedit `reference.docx`
  sesuai [ADR 0019](0019-reference-docx-as-single-visual-source.md).

## Bukti

- **List numbering berasal dari Markdown.** Uji dengan daftar Markdown berpenanda
  `a.` menghasilkan `w:numFmt w:val="numLowerLetter"` di `word/numbering.xml`.
  Artinya list numbering ditulis dari Markdown dan tidak bergantung pada
  `heading_numbering`.
- **Dokumen tugas pengguna** menjadi dasar nilai `none`/`grid`/`off`: tanpa
  nomor halaman, tabel `TableGrid` 0,5 pt, tanpa caption, dan tanpa heading
  numbering.

## Status

Diterima. Menambah key setting baru, menghidupkan key `profile`, memindahkan
setting ke dalam `reference.docx`, atau membuat reference generatif kembali
memerlukan ADR baru yang menandai ADR ini sebagai `superseded`.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)

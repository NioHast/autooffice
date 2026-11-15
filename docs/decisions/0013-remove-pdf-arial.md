# ADR 0013: Hapus PDF dan COM, Pakai Arial tanpa Embedding

- Status: diterima
- Tanggal: 2026-11-15
- Pemilik: integration owner
- Rujukan: ADR 0002, ADR 0004, ADR 0005, ADR 0006, ADR 0010, ADR 0011;
  [kontrak CLI](../contracts/cli.md), [kontrak design token](../contracts/design-token.md),
  dan [panduan ekspor PDF](../user/pdf-export.md)

## Konteks

AutoOffice sebelumnya membangun PDF dari DOCX dan PPTX lewat Microsoft Word
dan Microsoft PowerPoint COM di Windows. Jalur itu membawa dependensi
`pywin32`, lock proses Office, watchdog, snapshot PID, cleanup `taskkill`,
serta perilaku yang hanya dapat diuji di Windows dengan Office desktop.
Kegagalan COM juga membuat build tidak deterministik dan sulit dijalankan di
Linux, macOS, container, atau mesin tanpa lisensi Office.

Finalisasi field DOCX juga bergantung pada Word COM. Ketergantungan itu
membuat build DOCX ikut gagal atau menghasilkan field yang belum final di
lingkungan tanpa Word. Sementara itu, PDF bukan satu-satunya cara pengguna
menyerahkan dokumen: Word dan PowerPoint dapat mengekspor PDF secara manual
setelah review.

Font juga menjadi sumber kerumitan. Plus Jakarta Sans dibundel, divalidasi
hash-nya, ditanam ke PPTX lewat COM, dan diukur oleh layout engine. Penanaman
font menambah dependensi Office, memperbesar PPTX, dan membawa kewajiban
lisensi font. Arial sudah tersedia di sebagian besar sistem target dan
metriknya dapat dipakai untuk pengukuran deterministik lewat Liberation Sans.

## Keputusan

1. **PDF dihapus dari produk.** Tidak ada target `pdf`, tidak ada target
   `all`, dan tidak ada stage atau modul ekspor PDF. Target build hanya
   `docx` untuk `.md` serta `pptx` dan `slides` untuk `.yaml`.
2. **COM dihapus seluruhnya.** AutoOffice tidak memakai Microsoft Office COM,
   `pywin32`, PowerShell, `taskkill`, atau dependensi Windows-only untuk
   dokumen maupun presentasi. Tidak ada extra `windows`, tidak ada lock
   proses Office, dan tidak ada jalur build yang memerlukan Office desktop.
3. **Field dan TOC DOCX tidak diperbarui otomatis.** Pipeline menulis field
   native (`TOC`, `PAGEREF`, `SEQ`, `PAGE`) beserta instruksinya, tetapi tidak
   mengisi hasil field. Sebelum review atau ekspor PDF, pengguna membuka DOCX
   di Word, memilih seluruh dokumen dengan Ctrl+A, lalu menekan F9. Untuk
   daftar isi, pengguna juga dapat memakai References > Update Table.
4. **PPTX memakai Arial tanpa embedding.** Theme dan renderer memakai family
   `Arial`. AutoOffice tidak menanam font ke PPTX dan tidak membutuhkan font
   terpasang di mesin build.
5. **Plus Jakarta Sans keluar dari core theme dan aset.** Tidak ada lagi
   direktori `src/autooffice/assets/fonts/plus-jakarta-sans/`, metadata hash
   Plus Jakarta Sans, atau installer font Plus Jakarta Sans. Nama family di
   token typography adalah `Arial`. Aset Liberation Sans yang dibundel tetap
   memiliki metadata hash dan divalidasi di `src/autooffice/design/fonts.py`
   serta `autooffice doctor` karena dipakai untuk pengukuran layout, bukan
   untuk embedding atau tampilan family.
6. **Layout diukur dengan Liberation Sans.** Liberation Sans adalah font
   metrik-kompatibel Arial. Layout engine memakai metriknya untuk pengukuran
   teks yang deterministik tanpa bergantung pada font sistem. Hasil ukur
   diberlakukan sebagai ukuran Arial.
7. **PDF diekspor manual.** Pengguna membangun DOCX atau PPTX, mereview di
   Word atau PowerPoint, memperbarui field DOCX bila perlu, lalu mengekspor
   PDF dari aplikasi tersebut. Alur lengkap ada di
   [panduan ekspor PDF](../user/pdf-export.md).
8. **Sumber PDF/COM diarsipkan.** Implementasi lama disimpan di tag Git
   `pre-pdf-removal` dan branch `archive/pdf-com`. Keduanya tidak ada di
   working tree dan bukan sumber aktif. Pemulihan hanya dilakukan lewat ADR
   baru.

## Konsekuensi

- Build DOCX dan PPTX berjalan di Windows, Linux, dan macOS tanpa Office,
  `pywin32`, atau font yang dipasang pengguna.
- DOCX hasil build belum memiliki hasil field yang final. TOC, nomor halaman,
  daftar tabel, dan daftar gambar dapat tampil kosong atau memakai cache
  terakhir sampai pengguna menekan F9 di Word. Ini adalah perilaku yang
  didokumentasikan, bukan kegagalan build.
- PDF tidak lagi menjadi deliverable otomatis. Pengguna yang membutuhkan PDF
  menjalankan langkah manual dan bertanggung jawab atas review visual akhir.
- PPTX tidak membawa font. Di mesin tanpa Arial, PowerPoint, Google Slides,
  LibreOffice, atau aplikasi Android dapat mengganti Arial dengan font
  substitusi. Liberation Sans dipilih karena metriknya sama dengan Arial,
  sehingga tata letak yang dihitung tetap konsisten; bentuk glyph dapat
  berbeda.
- Tidak ada lagi smoke Office, marker tes `word`/`windows`, fixture PDF, atau
  golden PDF. Bukti output berfokus pada DOCX dan PPTX.
- Ukuran wheel mengecil karena aset font Plus Jakarta Sans dan adapter COM
  tidak lagi dipaketkan.
- Pengguna yang membutuhkan font tertanam pada PDF harus mengaktifkan opsi
  embedding saat mengekspor dari Word atau PowerPoint dan mematuhi lisensi
  font masing-masing.
- Gate `removed-features` memeriksa import, path, dependency, dan konfigurasi
  agar PDF, COM, `pywin32`, dan aset Plus Jakarta Sans tidak kembali.
- Dokumentasi lama yang menyebut PDF, COM, `pywin32`, Plus Jakarta Sans, atau
  target `all` ditandai superseded atau diganti. ADR historis tidak diubah
  isinya; hanya diberi banner superseded.

## Alternatif yang ditolak

- **Mempertahankan PDF lewat COM hanya di Windows.** Ditolak karena
  dependensi Office, `pywin32`, dan perilaku non-deterministik tetap ada.
- **Mengganti COM dengan LibreOffice headless.** Ditolak karena menambah
  dependensi eksternal besar, hasil visual berbeda, dan tetap membutuhkan
  aplikasi desktop.
- **Membuat PDF murni Python.** Ditolak karena tidak ada mesin PDF yang
  menghasilkan kualitas setara Word/PowerPoint untuk DOCX dan PPTX native.
- **Mempertahankan Plus Jakarta Sans tanpa embedding.** Ditolak karena font
  tidak tersedia di sistem target; substitusi akan mengubah metrik dan
  merusak layout.
- **Mengukur dengan Arial yang terpasang di mesin build.** Ditolak karena
  hasil bergantung pada mesin dan tidak deterministik.
- **Menanam Liberation Sans ke PPTX.** Ditolak karena produk memilih Arial
  dan tidak menanam font.

## Status

Diterima. Perubahan target build, font theme, mekanisme finalisasi field
DOCX, atau pengembalian COM/PDF memerlukan ADR baru. Sumber lama hanya boleh
dirujuk sebagai arsip di tag `pre-pdf-removal` dan branch `archive/pdf-com`.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)

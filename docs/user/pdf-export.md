# Ekspor PDF Manual

AutoOffice tidak lagi membangun PDF. Pipeline hanya menghasilkan DOCX dari
Markdown dan PPTX dari YAML. PDF dibuat manual dari Word atau PowerPoint
setelah dokumen direview. Keputusan ini dicatat di
[ADR 0013](../decisions/0013-remove-pdf-arial.md).

## Mengapa PDF tidak dibangun otomatis

- Build tidak lagi memakai Microsoft Office COM, `pywin32`, PowerShell, atau
  aplikasi Windows-only. AutoOffice berjalan tanpa Office di Windows, Linux,
  dan macOS.
- Build menjadi deterministik dan tidak bergantung pada versi Office, lisensi,
  atau state proses yang sedang berjalan.
- Tidak ada font yang ditanam ke PPTX. File build tidak membawa aset font
  pihak ketiga dan tidak memerlukan font terpasang di mesin build.
- Review akhir tetap dilakukan manusia. Ekspor manual memastikan pengguna
  melihat field, page break, dan kualitas cetak sebelum PDF diserahkan.

## Alur DOCX

1. Build DOCX:

   ```bash
   uv run autooffice build document.md --target docx
   ```

2. Buka DOCX hasil build di Microsoft Word.
3. Perbarui seluruh field: pilih seluruh dokumen dengan Ctrl+A, lalu tekan F9.
   Untuk daftar isi, pilih daftar isi lalu gunakan References > Update Table,
   atau jalankan Ctrl+A dan F9 sekali lagi.
4. Periksa daftar isi, daftar tabel, daftar gambar, nomor halaman, caption, dan
   page break. AutoOffice menulis field native, tetapi tidak mengisi hasil
   field. Tanpa langkah ini, daftar dapat tampil kosong atau memakai cache
   terakhir.
5. Simpan DOCX yang sudah direview bila ingin menyimpan hasil finalisasi.
6. Ekspor PDF: File > Save As atau File > Export > Create PDF/XPS. Pilih
   kualitas cetak atau standar distribusi yang dibutuhkan, lalu simpan.

Disarankan memakai stem `report_name` yang sama, misalnya `Tugas.docx`
menjadi `Tugas.pdf`, agar nama dokumen konsisten. Nama PDF tetap dipilih
pengguna saat ekspor.

## Alur PPTX

1. Build PPTX:

   ```bash
   uv run autooffice build deck.yaml --target pptx
   ```

2. Buka PPTX di Microsoft PowerPoint atau Google Slides.
3. Periksa teks, tabel, chart, gambar, dan catatan pembicara.
4. Ekspor PDF dari PowerPoint: File > Export > Create PDF/XPS. Dari Google
   Slides: File > Download > PDF Document.
5. Periksa PDF hasil ekspor sebelum dibagikan.

## Font dan embedding

- PPTX dari AutoOffice memakai family `Arial` dan tidak membawa font
  tertanam. AutoOffice hanya menulis nama family ke presentasi.
- Layout diukur dengan Liberation Sans, font metrik-kompatibel Arial. Ukuran
  dan posisi yang dihitung layout engine karena itu konsisten dengan Arial.
- Di Windows dan macOS, Arial umumnya sudah tersedia. Di Android, Linux, atau
  lingkungan tanpa Arial, aplikasi dapat mengganti Arial dengan Liberation
  Sans atau font substitusi lain. Tata letak umumnya tetap sama karena
  metriknya kompatibel, tetapi bentuk glyph dan rendering dapat berbeda.
- Bila PDF harus tampil identik di semua perangkat, aktifkan embedding font
  saat mengekspor dari Word atau PowerPoint. Di PowerPoint: File > Options >
  Save > Embed fonts in the file. Di Word: File > Options > Save > Embed
  fonts in the file.
- Embedding menambah ukuran berkas dan tunduk pada lisensi font. Pastikan
  lisensi Arial atau font pengganti mengizinkan embedding. AutoOffice tidak
  menanam font. Liberation Sans dibundel hanya untuk mengukur layout, bukan
  untuk ditanam atau ditampilkan sebagai family.

## Yang tidak lagi tersedia

- Target `pdf` dan `all`.
- Stage `pdf` dan adapter Word/PowerPoint COM.
- `pywin32`, extra `windows`, dan `autooffice doctor` untuk Office.
- Embedding font theme lama dan installer font yang sudah tidak ada.
- Golden PDF dan fixture PDF.

Sumber implementasi lama diarsipkan di tag Git `pre-pdf-removal` dan branch
`archive/pdf-com`. Keduanya bukan sumber aktif dan tidak ada di working tree.

## Dokumen terkait

- [Quickstart](quickstart.md) untuk alur build DOCX dan deck.
- [CLI AutoOffice](cli.md) untuk target dan flag yang masih tersedia.
- [Troubleshooting](troubleshooting.md) untuk masalah field dan output.
- [ADR 0013](../decisions/0013-remove-pdf-arial.md) untuk alasan keputusan.

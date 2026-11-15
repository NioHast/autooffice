# Field

Halaman ini menjelaskan field WordprocessingML yang ditulis pipeline.
Kontrak ada di [contracts/docx.md](../../contracts/docx.md).

`fields.py` menulis field kompleks lengkap: `begin`, `instrText`, `separate`,
hasil, dan `end`. Pipeline tidak menulis cache nomor halaman palsu. Word atau
aplikasi yang membuka dokumen mengisi hasil field. Atribut `w:dirty="true"`
hanya ditulis bila pemanggil memintanya; saat ini hanya field `STYLEREF` di
header body yang memakainya.

AutoOffice tidak menjalankan Word. Setelah build, field masih berisi hasil
kosong atau cache terakhir. Pengguna membuka DOCX di Word, menekan Ctrl+A lalu
F9, sebelum review atau ekspor PDF. Field bertanda `w:dirty` diperbarui Word
saat dokumen dibuka.

| Field | Dipakai untuk |
| --- | --- |
| `TOC \o "1-3" \h \z \u` | Daftar isi native di dalam `w:sdt`. |
| `TOC \c "Tabel"` | Daftar tabel. |
| `TOC \c "Gambar"` | Daftar gambar. |
| `SEQ Tabel \* ARABIC \s 1` | Nomor urut caption tabel per bab. |
| `SEQ Gambar \* ARABIC \s 1` | Nomor urut caption gambar per bab. |
| `PAGEREF` | Rujukan halaman bila diperlukan. |
| `PAGE` | Nomor halaman di header/footer. |
| `NUMPAGES` | Jumlah halaman bila diperlukan. |
| `STYLEREF "heading 1" \n` | Label nomor bab di header body bila `page.header_style_ref` diisi. |
| `STYLEREF "heading 1"` | Judul bab di header body (baris kedua). |

Header body memakai dua field `STYLEREF` karena heading memakai numbering
native Word:

- tanpa switch, Word mengembalikan teks judul saja;
- `\n` mengembalikan label nomor paragraf utuh (`BAB II`);
- `\s` hanya mengembalikan angka Romawi tanpa `BAB` (`II`), sehingga tidak
  dipakai.

Teks judul H1 `BAB_ROMAN` diawali `w:br`, jadi hasil field kedua menjadi
baris kedua header tanpa break tambahan. Untuk `ARABIC_DOTTED`, teks H1 satu
baris dan header menyisipkan `w:br` eksplisit di antara field nomor dan field
judul. Section yang memuat heading unnumbered memakai header `PAGE` saja agar
`\n` tidak menghasilkan `0`.

Tabel di atas mengasumsikan heading memakai `w:numPr` pada style. Bila
mekanisme numbering berubah lagi (mis. numbering level paragraf atau switch
lain), hasil field harus diukur ulang di Word; jangan menyalin switch tanpa
verifikasi.


Daftar tabel/gambar memakai hybrid: prefix bab literal dari caption, lalu field
`SEQ`. Detail keputusan ada di
[../decisions/0007-seq-hybrid.md](../decisions/0007-seq-hybrid.md).

## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [captions.md](captions.md) untuk caption dan `SEQ`.
- [bookmarks.md](bookmarks.md) untuk bookmark paragraf.
- [sections.md](sections.md) untuk field nomor halaman.
- [../pipeline/stages.md](../pipeline/stages.md) untuk stage `toc`,
  `page_numbers`, dan `lists`.

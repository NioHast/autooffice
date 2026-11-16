# Field

Halaman ini menjelaskan field WordprocessingML yang ditulis pipeline.
Kontrak ada di [contracts/docx.md](../../contracts/docx.md).

`fields.py` menulis field kompleks lengkap: `begin`, `instrText`, `separate`,
hasil, dan `end`. Pipeline tidak menulis cache nomor halaman palsu. Word atau
aplikasi yang membuka dokumen mengisi hasil field. Atribut `w:dirty="true"`
hanya ditulis bila pemanggil memintanya.

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

Header body hanya memuat field `PAGE`; tidak ada field header berjalan
(running header). Judul bab tidak disalin ke header.

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

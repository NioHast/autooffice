# Gambaran Pipeline

Halaman ini menjelaskan model eksekusi `Pipeline.run` dan invariant yang
berlaku lintas stage. Kontrak lengkap ada di
[contracts/docx.md](../../contracts/docx.md). Urutan stage ada di
[stages.md](stages.md).

`Pipeline.run(document_path, options)` memuat `document.md`, menjalankan stage
dengan urutan kanonik, menyimpan package DOCX satu kali, lalu selesai. Tidak
ada finalisasi Word atau ekspor PDF.

## Satu load dan satu save

- `pandoc` membuat package DOCX di workspace.
- `Pipeline` memuat package itu tepat satu kali.
- Semua stage sebelum `lists` memutasi package di memori.
- Adeu hook menambahkan bookmark dan menyiapkan manifest di memori.
- `Pipeline` memanggil `save` tepat satu kali.
- Manifest ditulis setelah save.

Stage tidak boleh memanggil `load` atau `save` target. `style_reference` boleh
memuat dan menyimpan `reference.docx` karena objeknya berbeda.

## Adeu hook

Adeu bukan stage kanonik, tetapi hook di dalam pass package:

1. Setelah `lists` dan sebelum save, `autooffice.docx.adeu.paragraph_ids`
   menambahkan bookmark `pNNNN`.
2. Manifest disiapkan di memori dengan `text_sha256`, `kind`, `heading_path`,
   dan status `protected`.
3. Setelah save, manifest ditulis ke `.laporan/manifest.json`.
4. Manifest diverifikasi setelah save; bookmark `pNNNN` yang hilang
   menggagalkan build.

Rincian ada di [adeu-integration.md](../adeu-integration.md).

## Idempotensi

Semua stage yang memutasi package dideklarasikan idempoten. Tidak ada stage
Word atau PDF yang menulis ulang package setelah save. Definisi:

- `document.xml` setelah c14n memiliki hash yang sama pada dua run;
- part non-target byte-identik;
- stage yang tidak memutasi package tidak mengubah artefak.

Stage yang gagal idempotensi adalah bug. Matriks lengkap ada di
[contracts/docx.md](../../contracts/docx.md).

## Logging

Logger pipeline dan logger stage memakai namespace internal pipeline.
Nama logger bukan API publik. Stage tidak memakai `print`. CLI memiliki stdout
dan stderr. Log tidak memuat seluruh isi dokumen atau data pribadi.

## Referensi resmi

Label registry yang dipakai halaman ini: `Pandoc manual` dan `PlantUML command
line`. URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [stages.md](stages.md) untuk urutan dan guard.
- [options.md](options.md) untuk flag build.
- [outputs.md](outputs.md) dan [artifacts.md](artifacts.md) untuk hasil build.
- [errors.md](errors.md) untuk kegagalan dan exit code.

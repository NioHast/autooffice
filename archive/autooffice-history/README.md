# Arsip Riwayat AutoOffice

Folder ini adalah arsip imutabel riwayat eksekusi AutoOffice. Isinya bukan
dokumentasi aktif dan bukan sumber kebenaran perilaku produk. Sumber kebenaran
tetap kode, test, kontrak di [`docs/contracts/`](../../docs/contracts/), dan
[`AUTO_OFFICE_EXECUTION_LOG.md`](../../AUTO_OFFICE_EXECUTION_LOG.md). Prosedur
rilis ada di [`docs/dev/release.md`](../../docs/dev/release.md).

Arsip dipakai untuk tiga hal:

1. menurunkan pelajaran dari kegagalan nyata, bukan dari teori;
2. menjalankan evaluasi regresi terhadap agent yang bekerja di repo ini;
3. memulihkan riwayat lengkap dari git bundle bila checkout lokal hilang.

## Isi Folder

| Berkas | Isi |
| --- | --- |
| `lessons.jsonl` | Satu objek JSON per entri log eksekusi, berisi masalah, resolusi, verifikasi, berkas, fase, dan commit fase. |
| `eval-cases.md` | 16 kasus evaluasi regresi yang diturunkan dari kegagalan nyata. Setiap kasus punya prompt, perilaku salah, hasil benar, dan perintah pemeriksaan. |
| `README.md` | Halaman ini: cara arsip dibuat, dipulihkan, disanitasi, dan aturan imutabilitas. |

## `lessons.jsonl`

Berkas ini memakai JSON Lines: satu objek JSON per baris, UTF-8, tanpa baris
kosong. Setiap objek memiliki kunci berikut.

| Kunci | Tipe | Arti |
| --- | --- | --- |
| `id` | string | Slug stabil dari tanggal dan judul, mis. `2026-11-14-f0-contract-freeze-dan-scaffold`. |
| `date` | string | Tanggal entri log, `YYYY-MM-DD`. |
| `phase` | string | `f0`, `f1`, `f2`, `f3`, `pdf-removal`, atau `release`. |
| `category` | string | `build`, `layout`, `renderer`, `docx`, `google`, `docs`, `gate`, `security`, `cleanup`, `com`, atau `other`. |
| `title` | string | Judul entri persis seperti di log. |
| `problem` | string | Isi bagian `Masalah`; beberapa butir digabung dengan `; `. |
| `resolution` | array string | Butir `Resolusi` atau `Resolusi/sisa`. |
| `verification` | array string | Hasil gate, test, smoke, atau bukti verifikasi lain dari entri. |
| `files` | array string | Isi `File yang berubah`, dipecah per path. Anotasi `(dihapus)` dan `(baru)` dipertahankan. |
| `commit` | string atau null | SHA pendek commit fase, atau `null` bila entri tidak jelas milik satu commit. |
| `evidence` | string | Anchor ke entri log, mis. `AUTO_OFFICE_EXECUTION_LOG.md#2026-11-14---f0-contract-freeze-dan-scaffold`. |

Catatan ekstraksi:

- Teks diambil dari log; tidak ada masalah, resolusi, atau verifikasi yang
  dikarang. Bila sebuah entri tidak punya bagian verifikasi eksplisit,
  `verification` berisi array kosong.
- Log kadang memakai singkatan path seperti `log`, `tests`, atau `docs`. Array
  `files` mempertahankan singkatan itu; hanya backtick, anotasi deskriptif, dan
  pemisah koma yang dinormalkan.
- Bila hasil test ditulis di dalam `Resolusi` (misalnya angka `passed`), hasil
  itu disalin ke `verification` agar bukti tetap terbaca mesin.
- `problem` adalah string, bukan array. Butir `Masalah` yang lebih dari satu
  digabung dengan `; ` tanpa mengubah isi.
- Entri yang menyatakan tidak ada perubahan kode memiliki `files` kosong.
- Nama historis seperti package lama dan adapter PowerShell sengaja tetap ada
  di arsip. Checker legacy harus mengecualikan folder arsip, bukan menyunting
  arsip untuk menghilangkan nama itu.

### Jumlah Entri

Log memiliki **48 entri bertanggal**. Perintah `grep '^## '` menghasilkan 49
heading karena `## Format` adalah template penulisan, bukan entri eksekusi.
Spesifikasi awal menyebut 49 entri; hitungan aktual yang dapat dipertanggungjawabkan
adalah 48. Karena itu `lessons.jsonl` berisi **48 baris**, satu baris per entri
bertanggal. Jangan menambah entri rekaan untuk mengejar angka 49.

Fase `release` disediakan di skema, tetapi tidak dipakai: log tidak memiliki
entri rilis. Commit rilis `98287f1` (`chore: release 1.0.0`) tidak punya entri
log dan tidak dipakai sebagai `commit` oleh record mana pun.

### Pemetaan Commit

Commit diisi pada level fase, bukan per entri:

| Fase | Commit | Cakupan |
| --- | --- | --- |
| `f0` | `3b4ab27` | Scaffold dan pembekuan kontrak F0. Merge commit `147a4de` dicatat di `resolution`, bukan di `commit`. |
| `f1` dan `f2` | `34e472d` | Implementasi DOCX, deck, slides, dan pipeline PDF. F1 dan F2 berjalan tumpang tindih dan mendarat di commit yang sama. |
| `f3` | `711de82` | Pembersihan legacy, gate kualitas, dan penyelesaian F3. |
| `pdf-removal` | `119d558` | Penghapusan PDF/COM dan peralihan theme deck ke Arial. |
| `release` | — | Tidak ada entri log; rilis ditandai tag `v1.0.0` pada `98287f1`. |

Semua 48 entri dapat dipetakan dengan jelas; tidak ada `commit` bernilai
`null`. Pemetaan ini sengaja kasar: satu commit fase dapat memuat banyak entri,
dan satu entri tidak boleh dianggap dimiliki satu commit tunggal. Peta riwayat
yang lebih rinci dibuat oleh exporter sebagai `history-map.md`; peta itu
memetakan entri ke commit yang menyentuh path yang disebut entri, bukan ke
commit fase.

`phase` diambil dari label fase pertama pada `Fase/lane`. Bila lane tidak
menyebut label fase (mis. `code quality` atau `correctness review`), entri
ditempatkan pada fase F1/F2 tempat pekerjaan itu mendarat. `category` dipilih
dari topik dominan entri, bukan dari nama lane.

## `eval-cases.md`

Setiap kasus punya `ID`, `Sumber` (id entri `lessons.jsonl`), `Prompt`,
`Perilaku salah`, `Hasil benar`, dan `Cara memeriksa`. Prompt sengaja berupa
instruksi yang mengarah ke kesalahan lama; agent yang benar harus menolak atau
memperbaiki instruksi itu, lalu membuktikan hasilnya dengan perintah yang
diberikan.

Kasus mencakup target `pdf`/`all`, embedding font, dokumen basi, kode mati,
packaging/wheel, cleanup registry, dependency Windows-only, penulisan ulang
history, dependency tanpa lock, theme Arial, test mock, referensi installer
font, fallback senyap, batas ZIP, keamanan path, dan caption chart.

## Cara Arsip Dibuat per Rilis

Arsip dibuat dari tag rilis, bukan dari working tree. Pada langkah 6 prosedur
rilis, jalankan:

```bash
uv run python tools/history/export_archive.py --tag vX.Y.Z
uv run python tools/history/export_archive.py --tag vX.Y.Z --upload
```

Perintah pertama menulis arsip ke `dist/history-vX.Y.Z/` (atau `--out DIR`).
Perintah kedua mengunggah berkas arsip ke GitHub release `vX.Y.Z` tanpa membuat
tag baru.

Exporter menghasilkan:

- `AUTO_OFFICE_EXECUTION_LOG.md` persis seperti pada tag;
- `autooffice-vX.Y.Z.bundle`, git bundle seluruh ref yang sudah diverifikasi;
- `history-map.md`, peta entri log ke path dan commit yang menyentuh path itu;
- salinan `lessons.jsonl`, `eval-cases.md`, dan `docs/dev/agent-rules.md` bila
  berkas itu ada pada tag;
- `SHA256SUMS` untuk semua berkas arsip.

README ini tidak disalin sebagai berkas lepas; isinya tetap tersimpan di dalam
bundle karena bundle memuat seluruh ref. Exporter hanya menyalin berkas data
yang tercantum di `OPTIONAL_FILES`.

Karena exporter membaca blob pada tag, `lessons.jsonl`, `eval-cases.md`, dan
README ini harus sudah di-commit sebelum tag rilis dibuat. Bila berkas belum
ada pada tag, exporter melewatinya tanpa gagal. Tag `v1.0.0` sudah dibuat
sebelum folder arsip ini ada, sehingga bundle `v1.0.0` tidak memuat ketiga
berkas ini. Arsip ini mulai ikut pada tag rilis berikutnya; tag lama tidak
boleh dibuat ulang.

Verifikasi checksum sebelum memakai arsip:

```bash
sha256sum -c SHA256SUMS
```

## Restore dari Bundle

Bundle memuat seluruh ref, termasuk tag rilis. Setiap rilis menghasilkan
`autooffice-<tag>.bundle`. Pulihkan di direktori kosong:

```bash
git bundle verify autooffice-v1.0.0.bundle
git clone autooffice-v1.0.0.bundle autooffice-v1.0.0
cd autooffice-v1.0.0
git checkout v1.0.0
git fsck --full
uv sync --extra dev
uv run autooffice --version
```

Setelah restore, jalankan gate penuh sebelum memakai hasil restore untuk
perubahan baru:

```bash
uv run python tools/quality/gate.py
```

Bila clone dari bundle belum punya remote, tambahkan remote asli secara manual.
Jangan mengubah isi bundle; bundle adalah artefak arsip, bukan working copy.

## Tag Permanen

Dua tag permanen yang tidak boleh dihapus atau dipindahkan:

| Tag | Commit | Arti |
| --- | --- | --- |
| `pre-pdf-removal` | `711de82` | Checkpoint terakhir F3, tepat sebelum PDF/COM dihapus di `119d558`. |
| `backup/main-before-msg-rewrite` | `75c496b` | Backup lineage lama sebelum pesan commit ditulis ulang. History-nya terpisah dari `main` dan tidak dimaksudkan untuk di-merge. |

Tag rilis `vX.Y.Z` juga imutabel. `v1.0.0` adalah annotated tag yang menunjuk
commit `98287f1`. Satu versi hanya boleh punya satu tag; jangan membuat ulang
atau memindahkan tag yang sudah dipublikasikan.

## Peringatan Sanitasi

Log eksekusi disalin apa adanya ke arsip. Log dan turunannya dapat memuat:

- path lokal dan path sistem, mis. `%SystemRoot%`, `AppData`, `.venv`, atau
  direktori kerja pengguna;
- nama registry, nama mesin, nama branch lokal, dan keluaran perintah;
- bukti instalasi atau cleanup yang spesifik mesin.

Sebelum arsip dipublikasikan di luar penyimpanan tepercaya:

1. jalankan pemeriksaan sanitasi pada log dan berkas turunannya;
2. hapus path absolut, nama pengguna, nama mesin, dan token/kredensial OAuth;
3. pertahankan perintah dan hasil yang reproducible, buang detail lingkungan
   yang tidak diperlukan;
4. jangan menaruh kredensial, token, atau isi `.env` di log sejak awal.

Sanitasi dilakukan **sebelum** tag dan ekspor. Setelah arsip dipublikasikan,
jangan menyunting salinan yang sudah dirilis.

## Imutabilitas Arsip

- Arsip yang sudah dirilis tidak pernah ditulis ulang, diganti, atau dihapus.
- Nama tag dan nama berkas arsip tidak dipakai ulang untuk isi yang berbeda.
- Koreksi dilakukan dengan rilis baru `vX.Y.(Z+1)`, bukan dengan memperbaiki
  arsip lama.
- `lessons.jsonl` dan `eval-cases.md` pada tag tertentu bersifat beku. Perubahan
  untuk rilis berikutnya ditulis di working tree, lalu ikut pada tag berikutnya.

Aturan ini menjaga agar bundle, checksum, dan tautan `evidence` tetap dapat
diverifikasi bertahun-tahun kemudian.

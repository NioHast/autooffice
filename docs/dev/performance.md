# Performance

Halaman ini menjelaskan tes performa deck besar di `tests/performance/`
dan optimasi cache serta indeks yang sudah diterapkan. Tes tersebut menjaga
agar kompilasi, pembentukan key manifest, dan layout plan tetap selesai dalam
waktu wajar saat jumlah slide bertambah. Tes ini bukan benchmark mikro dan
tidak memakai ambang waktu per operasi.

## Cakupan

`test_large_deck.py` membangun deck YAML sintetis di `tmp_path`. Setiap slide
memakai layout custom dengan campuran konten yang sama:

- teks judul dan lead;
- bullets;
- tabel;
- chart batang;
- referensi gambar PNG kecil;
- notes pembicara.

Test default (100 slide) melakukan kompilasi ke `DeckIR` dan `KeyManifest`,
lalu membuat `LayoutPlan` untuk seluruh slide. Assertion utamanya:

- compile dan plan selesai di bawah 15 detik pada mesin pengembangan;
- jumlah key kira-kira 100 kali deck satu slide (toleransi 5 persen);
- tidak ada key duplikat;
- dua run compile dan plan menghasilkan output yang identik.

Test default tidak merender PPTX. Render 100 slide terlalu mahal untuk suite
rutin.

## Marker slow

Test berat memakai `@pytest.mark.slow`:

| Test | Beban |
| --- | --- |
| `test_500_slide_deck_compiles_within_budget` | Kompilasi 500 slide tanpa plan atau render. |
| `test_ten_slide_deck_renders_to_pptx` | Render 10 slide ke PPTX dan cek coverage. |

`pytest.ini` menambahkan marker `slow` dan `addopts = -m "not slow"`. Artinya
run default melewati test berat secara otomatis tanpa perlu flag tambahan.

## Menjalankan

Jalankan test default dari akar repo:

```bash
uv run pytest tests/performance -q
```

Jalankan hanya test berat:

```bash
uv run pytest tests/performance -q -m slow
```

Jalankan eksplisit tanpa test berat bila `addopts` diubah di masa depan:

```bash
uv run pytest tests/performance -q -m "not slow"
```

Jalankan satu test tertentu:

```bash
uv run pytest tests/performance/test_large_deck.py -q -k deterministic
```

## Cache dan indeks

Beberapa optimasi sudah diterapkan dan dijaga test perilaku, bukan hanya
benchmark:

| Area | Mekanisme | Efek terukur |
| --- | --- | --- |
| PlantUML DOCX | Cache persisten `.laporan/cache/plantuml` dengan kunci hash render + opsi + fingerprint executable, plus sidecar untuk fallback tanpa engine. | 4x cold, 2,4x warm |
| Pengukuran deck | `lru_cache` 8.192 entri untuk `measure_text` dan `measure_code_text`; kunci memakai nilai tipografi yang sudah diresolusi. | 2,62x cold, 19,3x warm |
| Coverage deck | Indeks binding per key dan per slide sehingga plan dan report tidak memindai seluruh binding berulang kali. | 16x dan 7,86x |
| Perubahan pohon DOCX | `tree_digest` menghitung SHA-256 serialisasi langsung, menggantikan C14N pada pohon yang sama. | sekitar 12x |
| Versi PlantUML | `Implementation-Version` dibaca dari manifest jar tanpa JVM; subprocess `--version` hanya fallback. | 11,5x |

Angka di atas berasal dari pengukuran mesin pengembangan dan bukan ambang test,
sehingga boleh berubah antar-mesin. Yang dijaga suite adalah perilaku: cache
tidak memanggil engine saat hit, invalidasi cache benar, hasil pengukuran cache
sama dengan jalur non-cache, dan plan coverage tetap cocok dengan referensi.
Rincian kontrak cache PlantUML ada di
[contracts/plantuml.md](../contracts/plantuml.md#cache).

## Batas dan interpretasi

- Ambang 15 detik untuk 100 slide sengaja longgar; mesin lambat atau cold start
  font masih punya ruang. Jangan mengubahnya menjadi ambang mikrodetik.
- Rasio key memakai toleransi karena perubahan konten suatu saat boleh mengubah
  jumlah key per slide. Yang dijaga adalah skalanya, bukan angka absolut.
- Batas 30 detik untuk kompilasi 500 slide adalah smoke, bukan target perf.
- Kegagalan determinisme berarti urutan slide, binding, atau geometri plan
  berubah antar-run. Periksa sumber non-deterministik seperti iterasi `set`
  atau path/working directory, bukan menaikkan toleransi.
- Tes tidak memakai jaringan atau Office. Render PPTX memakai `python-pptx`
  murni.

## Terkait

- [testing.md](testing.md): marker, golden baseline, dan perintah suite.
- [test-quality.md](test-quality.md): kriteria memilih kasus test.
- [quality-gates.md](quality-gates.md): urutan gate lokal.

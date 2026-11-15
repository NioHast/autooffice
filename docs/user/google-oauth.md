# Setup OAuth Google untuk AutoOffice Slides

Panduan ini menghubungkan AutoOffice ke Google Drive, Google Slides, dan
Google Sheets memakai **OAuth user flow** dari akun Google Anda. AutoOffice
hanya mendukung alur pengguna ini; service account tidak didukung. File yang
dibuat akan dimiliki akun Google yang memberi izin.

Semua perintah dijalankan dari akar repo AutoOffice di PowerShell. Setelah
selesai, token tersimpan di luar repo, `autooffice doctor --target slides`
siap, dan deck demo dapat di-push, di-diff, di-pull, serta di-apply ke Google
Slides.

## Daftar isi

- [1. Prasyarat](#1-prasyarat)
- [2. Aktifkan API Google](#2-aktifkan-api-google)
- [3. Konfigurasikan OAuth consent screen](#3-konfigurasikan-oauth-consent-screen)
- [4. Buat OAuth client Desktop app](#4-buat-oauth-client-desktop-app)
- [5. Set environment PowerShell](#5-set-environment-powershell)
- [6. Pasang extra google](#6-pasang-extra-google)
- [7. Login OAuth](#7-login-oauth)
- [8. Verifikasi token dan doctor](#8-verifikasi-token-dan-doctor)
- [9. Live smoke test Slides](#9-live-smoke-test-slides)
- [10. Troubleshooting](#10-troubleshooting)
- [11. Keamanan](#11-keamanan)
- [12. Testing vs Production](#12-testing-vs-production)
- [Referensi](#referensi)

## 1. Prasyarat

Siapkan:

- Akun Google yang akan menjadi pemilik presentasi dan spreadsheet. Akun ini
  harus ditambahkan sebagai pengguna uji selama aplikasi masih berstatus
  **Testing**.
- Project Google Cloud. Satu project cukup untuk client OAuth dan ketiga API.
- Repo AutoOffice dan `uv`. Repo mensyaratkan Python 3.15; `uv` dapat
  mengelola versi Python tersebut.
- PowerShell 5.1 atau PowerShell 7. Perintah `$env:` dan here-string di
  panduan ini bekerja di keduanya.

Periksa `uv` dan siapkan Python:

```powershell
uv --version
uv python install 3.15
```

Jalankan semua perintah berikutnya dari akar repo, bukan dari folder sementara.
`uv run` akan memakai environment project yang sama.

## 2. Aktifkan API Google

1. Buka [Google Cloud Console](https://console.cloud.google.com/) dan pilih
   atau buat project. Pastikan project yang aktif adalah project yang akan
   dipakai untuk client OAuth.
2. Buka **APIs & Services** > **Library**.
3. Cari dan aktifkan ketiga API berikut. Tunggu beberapa menit setelah
   mengaktifkannya.

| API | Dipakai untuk |
| --- | --- |
| Google Drive API | Mengunggah PPTX staging dan mengubahnya menjadi Google Slides. |
| Google Slides API | Membaca dan menulis teks, tabel native, notes, dan placeholder chart. |
| Google Sheets API | Membuat workbook dan linked chart untuk chart block. |

Ketiga API harus aktif di project yang sama dengan OAuth client. Bila salah
satu belum aktif, push dapat gagal dengan `accessNotConfigured` atau
`insufficientPermissions`.

## 3. Konfigurasikan OAuth consent screen

Di UI Google Cloud terbaru, pengaturan ini berada di **Google Auth Platform**.
Di dokumentasi lama, menu yang sama disebut **OAuth consent screen**. Isi
bagian berikut.

1. Buka **Google Auth Platform** > **Branding** untuk mengisi app info. Isi
   **App name**, **User support email**, dan **Developer contact information**.
   Nama aplikasi boleh `AutoOffice`; email harus email yang Anda pantau.
2. Buka **Audience**. Pilih **User type: External**. Untuk akun Google biasa,
   External adalah satu-satunya pilihan. Di Google Workspace organisasi,
   **Internal** juga tersedia, tetapi panduan ini memakai External/Testing agar
   cocok untuk akun pribadi.
3. Pastikan **Publishing status: Testing**. Tambahkan akun Google yang akan
   dipakai login ke **Test users**. Akun harus persis sama dengan akun yang
   dipilih di browser saat consent. Batas pengguna uji adalah 100 akun.
4. Buka **Data access** > **Add or remove scopes**. Tambahkan ketiga scope
   berikut, lalu simpan.

| Scope | URL lengkap | Fungsi |
| --- | --- | --- |
| `drive.file` | `https://www.googleapis.com/auth/drive.file` | Akses hanya ke file yang dibuat atau dibuka oleh AutoOffice. |
| `presentations` | `https://www.googleapis.com/auth/presentations` | Baca dan tulis presentasi Google Slides. |
| `spreadsheets` | `https://www.googleapis.com/auth/spreadsheets` | Buat dan ubah spreadsheet serta linked chart. |

AutoOffice meminta tepat ketiga scope tersebut. Jangan menghapus salah satunya.
Bila satu scope tidak diminta atau tidak disetujui, operasi Slides atau Sheets
dapat gagal dengan `insufficientPermissions`; ulangi login dan setujui semua
scope. `presentations` dan `spreadsheets` termasuk scope sensitif; `drive.file`
memberi akses terbatas per file.

Selama status Testing, layar consent dapat menampilkan peringatan bahwa aplikasi
belum diverifikasi Google. Peringatan ini normal untuk project dan akun uji Anda
sendiri.

## 4. Buat OAuth client Desktop app

1. Buka **Google Auth Platform** > **Clients**, atau **APIs & Services** >
   **Credentials**.
2. Pilih **Create client** atau **Create credentials** > **OAuth client ID**.
3. Pilih **Application type: Desktop app**. Jangan pilih **Web application**.
4. Beri nama, misalnya `AutoOffice desktop`, lalu klik **Create**.
5. Salin **Client ID** dan **Client secret**. Simpan secret di password manager
   atau tempat aman lain. Jangan menyimpan file JSON client di dalam repo.

Client bertipe Desktop app tidak memerlukan pendaftaran redirect URI. AutoOffice
membuka browser dan menerima callback lewat server localhost sementara. Bila
Anda sudah terlanjur membuat client bertipe Web application, buat client baru
bertipe Desktop app; jangan memakai ulang client Web application.

## 5. Set environment PowerShell

Set client ID dan secret untuk sesi PowerShell saat ini:

```powershell
$env:GOOGLE_CLIENT_ID = "<client-id>.apps.googleusercontent.com"
$env:GOOGLE_CLIENT_SECRET = "<client-secret>"
```

Nilai di atas hanya contoh. Ganti dengan client ID dan secret dari langkah
sebelumnya. Client ID bukan rahasia, tetapi client secret harus diperlakukan
sebagai kredensial sensitif.

Secara opsional, tentukan lokasi token:

```powershell
$env:AUTOOFFICE_GOOGLE_TOKEN = Join-Path $env:LOCALAPPDATA "autooffice\google\token.json"
```

Bila `AUTOOFFICE_GOOGLE_TOKEN` tidak diisi, AutoOffice memakai lokasi default:

| Kondisi | Lokasi token |
| --- | --- |
| Windows dengan `LOCALAPPDATA` | `%LOCALAPPDATA%\autooffice\google\token.json` |
| Windows tanpa `LOCALAPPDATA` | `%APPDATA%\autooffice\google\token.json` |
| Linux/macOS dengan `XDG_CONFIG_HOME` | `$XDG_CONFIG_HOME/autooffice/google/token.json` |
| Linux/macOS tanpa `XDG_CONFIG_HOME` | `~/.config/autooffice/google/token.json` |
| Path kustom | Nilai `AUTOOFFICE_GOOGLE_TOKEN` |

Path kustom harus berada di luar repo. `TokenStore` menolak path yang berada di
bawah direktori yang memiliki `.git`, sehingga path default tidak berada di
dalam repo. Jangan mengarahkan token ke folder kerja deck.

Untuk login interaktif, biarkan `GOOGLE_REDIRECT_URI` tidak di-set. Helper login
memakai redirect localhost default. Bila variabel itu sudah terlanjur diisi,
hapus dari sesi:

```powershell
Remove-Item Env:GOOGLE_REDIRECT_URI -ErrorAction SilentlyContinue
```

Verifikasi environment tanpa mencetak secret:

```powershell
uv run python -c "from autooffice.google import OAuthSettings; settings = OAuthSettings.from_environment(); print(settings.client_id); print(settings.redirect_uri)"
```

Jika perintah ini gagal dengan pesan `Kredensial Google OAuth tidak ditemukan`,
berarti `GOOGLE_CLIENT_ID` atau `GOOGLE_CLIENT_SECRET` belum terbaca di shell
yang sedang dipakai. Nilai redirect default `http://localhost:4173/oauth2callback`
adalah kontrak `OAuthSettings`; helper login memakai server loopback dengan port
sementara, dan client Desktop app menerima loopback tersebut tanpa pendaftaran
redirect URI tambahan.

## 6. Pasang extra google

Dari akar repo, pasang dependensi Google:

```powershell
uv sync --extra google
```

Pastikan modul Google dapat diimpor:

```powershell
uv run python -c "import googleapiclient, google_auth_oauthlib; print('extra google siap')"
```

Extra `google` memasang `google-api-python-client` dan
`google-auth-oauthlib`. Tanpa extra ini, target `slides` akan gagal dengan
pesan yang meminta `uv sync --extra google`.

## 7. Login OAuth

Jalankan login interaktif. Perintah ini memakai `OAuthSettings`, `TokenStore`,
dan `run_interactive_authorization` dari `autooffice.google`:

```powershell
@'
from autooffice.google import OAuthSettings, TokenStore, run_interactive_authorization

settings = OAuthSettings.from_environment()
store = TokenStore.from_environment()
run_interactive_authorization(settings, store)
print(f"Token tersimpan di {store.path}")
'@ | uv run python -
```

Browser akan terbuka. Pilih akun yang sudah ditambahkan sebagai test user,
setujui ketiga scope, lalu tunggu sampai halaman callback localhost menampilkan
pesan sukses. AutoOffice memakai `access_type=offline` dan `prompt=consent`
sehingga token yang disimpan memuat refresh token.

Bila browser tidak terbuka otomatis, jalankan variasi berikut dengan
`open_browser=False`:

```powershell
@'
from autooffice.google import OAuthSettings, TokenStore, run_interactive_authorization

run_interactive_authorization(
    OAuthSettings.from_environment(),
    TokenStore.from_environment(),
    open_browser=False,
)
'@ | uv run python -
```

Terminal akan mencetak URL consent. Buka URL itu secara manual di browser,
setujui scope, lalu kembali ke terminal. Fallback ini tetap membutuhkan browser
yang dapat mengakses `localhost` di mesin yang sama. Untuk mesin remote tanpa
browser, gunakan flow manual `create_flow` dan `exchange_code`; helper
`run_interactive_authorization` tidak dirancang untuk lingkungan headless.

Login menulis token secara atomik ke path `TokenStore`. Token berisi access
token, refresh token, client ID, dan client secret yang dipakai untuk refresh.
Jangan menyalin isi token ke issue, log, atau chat.

## 8. Verifikasi token dan doctor

Cetak path token yang benar-benar dipakai, lalu periksa keberadaannya:

```powershell
$tokenPath = uv run python -c "from autooffice.google import TokenStore; print(TokenStore.from_environment().path)"
$tokenPath
Test-Path $tokenPath
```

`Test-Path` harus menghasilkan `True`. Untuk memastikan scope yang tersimpan
sudah lengkap, baca hanya field `scopes`:

```powershell
$token = Get-Content $tokenPath -Raw | ConvertFrom-Json
$token.scopes
$token.expiry
```

Output `scopes` harus memuat ketiga URL scope dari langkah 3. Jangan mencetak
seluruh objek token karena berisi kredensial. Build berikutnya memuat token ini
dan me-refresh access token bila kedaluwarsa; kegagalan refresh akan muncul
sebagai `invalid_grant` atau `Refresh token Google gagal`.

Jalankan pemeriksaan lokal untuk target Slides:

```powershell
uv run autooffice doctor --target slides
```

`doctor` memeriksa Python, aset font, extra Google, dan kredensial OAuth lokal
tanpa memanggil jaringan. Pemeriksaan `google` harus berstatus siap. Keberhasilan
`doctor` berarti extra dan file token tersedia; ini belum membuktikan token masih
valid atau scope masih diberikan. Validasi jaringan dilakukan pada live smoke
test berikut.

## 9. Live smoke test Slides

Smoke test ini membuat file nyata di Google Drive akun Anda. Gunakan akun uji,
bukan akun produksi.

Salin deck demo ke folder sementara, hapus artefak build yang terbawa, lalu
periksa sumbernya:

```powershell
$smoke = Join-Path $env:TEMP "autooffice-slides-smoke"
Remove-Item -Recurse -Force $smoke -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force examples\demo-deck $smoke
Remove-Item -Recurse -Force "$smoke\out", "$smoke\.autooffice", "$smoke\.autooffice-build" -ErrorAction SilentlyContinue
uv run autooffice check "$smoke\deck.yaml"
```

Push pertama membuat spreadsheet, linked chart, presentasi Slides, dan state
lokal:

```powershell
uv run autooffice build "$smoke\deck.yaml" --target slides --sync push
```

Baca URL presentasi dan spreadsheet dari state, lalu buka presentasi:

```powershell
$state = Get-Content "$smoke\.autooffice\state\deck.json" -Raw | ConvertFrom-Json
$state.presentation_url
$state.spreadsheet_url
Start-Process $state.presentation_url
```

Ubah satu teks ber-key di Google Slides, misalnya judul slide pertama dengan key
`s01.title.text`, lalu simpan. Setelah itu jalankan ketiga mode review:

```powershell
uv run autooffice build "$smoke\deck.yaml" --target slides --sync diff
uv run autooffice build "$smoke\deck.yaml" --target slides --sync pull
uv run autooffice build "$smoke\deck.yaml" --target slides --sync apply
```

Hasilnya berada di `.autooffice/review/` di samping `deck.yaml`:

| Mode | Output | Isi |
| --- | --- | --- |
| `diff` | `deck.diff.json` | Report perubahan teks remote terhadap YAML. |
| `pull` | `deck.pulled.yaml` | Salinan YAML baru dengan teks remote yang berubah. |
| `apply` | `deck.applied.yaml` | Salinan YAML baru hasil penerapan diff. |

Periksa berkas review:

```powershell
Get-ChildItem "$smoke\.autooffice\review"
Get-Content "$smoke\.autooffice\review\deck.diff.json" -Raw
```

Mode `diff`, `pull`, dan `apply` tidak merender ulang dan tidak pernah mengubah
`$smoke\deck.yaml`. Selain berkas review, ketiga mode memperbarui state dengan
revision ID remote; `pull` dan `apply` tidak menulis YAML sumber. Mode tersebut
memerlukan state dari push pertama; tanpa state, CLI akan meminta Anda
menjalankan push lebih dulu.

> **Catatan target:** target `all` sudah dihapus dari CLI dan kini ditolak
> sebagai target tidak valid dengan kode keluar 2. Tulis target eksplisit;
> untuk alur ini gunakan `--target slides`. Flag `--sync` hanya valid bila
> target berisi `slides`, jadi jangan menggabungkannya dengan target lain pada
> alur ini.

Setelah selesai, hapus presentasi dan spreadsheet lewat URL di atas, lalu hapus
folder sementara:

```powershell
Remove-Item -Recurse -Force $smoke
```

## 10. Troubleshooting

| Gejala | Penyebab umum | Tindakan |
| --- | --- | --- |
| `Kredensial Google OAuth tidak ditemukan` | `GOOGLE_CLIENT_ID` atau `GOOGLE_CLIENT_SECRET` tidak di-set di shell saat ini, misalnya karena membuka terminal baru. | Set ulang kedua variabel di sesi yang sama, lalu ulangi login. Pastikan tidak ada spasi atau tanda kutip yang ikut tersimpan. |
| `redirect_uri_mismatch` | Client OAuth bertipe **Web application**, bukan **Desktop app**, atau `GOOGLE_REDIRECT_URI` menunjuk URL yang tidak terdaftar. | Buat client **Desktop app** baru, set client ID/secret-nya, hapus `GOOGLE_REDIRECT_URI`, lalu login ulang. Helper interaktif menolak redirect kustom sebelum menghubungi Google. |
| `access_denied` | Anda menolak consent, akun belum ada di **Test users**, atau akun diblokir kebijakan organisasi. | Tambahkan akun Google yang tepat ke **Audience** > **Test users**, setujui semua scope, lalu ulangi login. Bila akun Workspace diblokir admin, minta admin mengizinkan aplikasi. |
| `invalid_grant` atau `Refresh token Google gagal` | Refresh token kedaluwarsa atau dicabut. Penyebab tersering adalah status External/Testing yang memberi token 7 hari; bisa juga karena akses dicabut pengguna, token tidak dipakai lama, atau batas token per akun terlampaui. | Hapus token lokal, login ulang, lalu ulangi smoke test. Untuk pemakaian jangka panjang, pindahkan aplikasi ke Production sebelum login ulang. |
| `insufficientPermissions` atau `PERMISSION_DENIED` karena scope | Salah satu API belum aktif, salah satu scope tidak disetujui, atau token berasal dari project/client lain. | Aktifkan Drive, Slides, dan Sheets API di project yang sama; tambahkan ketiga scope di **Data access**; hapus token; login ulang dan setujui semua scope. |
| Browser tidak terbuka atau URL consent tidak muncul | Browser default tidak merespons, atau lingkungan tidak punya GUI. | Jalankan login dengan `open_browser=False`, salin URL dari terminal ke browser, dan pastikan callback `localhost` dapat dijangkau. Untuk mesin remote tanpa browser, gunakan flow manual `create_flow` dan `exchange_code`. |

## 11. Keamanan

- Jangan pernah commit client secret, file JSON OAuth client, atau token ke Git.
  Client secret boleh berada di environment atau password manager; file token
  lokal juga memuatnya, jadi perlakukan token sebagai kredensial.
- Token default sudah berada di luar repo. Path kustom lewat
  `AUTOOFFICE_GOOGLE_TOKEN` juga ditolak bila berada di bawah direktori yang
  memiliki `.git`. Jangan memindahkan token ke folder deck untuk "kemudahan".
- Token memuat refresh token dan client secret. Jangan mencetak isi token,
  melampirkannya ke issue, atau mengirimkannya lewat chat. Cukup cetak path dan
  daftar scope seperti pada langkah verifikasi.
- State `.autooffice/state/<stem>.json` menyimpan ID/URL presentasi dan
  spreadsheet serta metadata sinkronisasi, bukan token. Meskipun begitu, jangan
  commit direktori `.autooffice/` karena itu artefak lokal.
- Untuk mencabut akses, buka setelan Keamanan akun Google Anda, pilih
  **Third-party apps & services** (di UI lama: **Apps with account access**),
  lalu hapus akses AutoOffice. Setelah itu hapus token lokal:

```powershell
uv run python -c "from autooffice.google import TokenStore; print(TokenStore.from_environment().clear() or 'token dihapus')"
```

Bila token atau secret diduga bocor, cabut akses, hapus token, dan reset client
secret di Google Cloud Console. Login ulang setelah secret baru dipasang.

## 12. Testing vs Production

Status **External + Testing** cocok untuk pengembangan lokal dan smoke test,
tetapi memiliki konsekuensi penting:

| Aspek | External + Testing | Production |
| --- | --- | --- |
| Siapa yang dapat login | Hanya akun di **Test users**, maksimal 100 akun. | Semua pengguna Google (External); Internal terbatas pada organisasi. |
| Refresh token | Kedaluwarsa 7 hari sejak consent untuk scope non-identitas seperti scope AutoOffice. | Umumnya berlaku sampai dicabut atau tidak dipakai sekitar enam bulan. |
| Verifikasi | Tidak diperlukan untuk pengujian. | Verifikasi brand dan scope sensitif diperlukan agar aplikasi publik dapat memakai scope tersebut tanpa peringatan dan batas pengguna. |
| Cocok untuk | Pengembangan, demo, dan smoke test. | Pemakaian berulang, tim, atau otomasi jangka panjang. |

Karena `presentations` dan `spreadsheets` adalah scope sensitif, aplikasi
External yang dipublikasikan untuk pengguna umum perlu menyelesaikan verifikasi
scope. Status **In production** dan status **verified** adalah dua hal berbeda:
publikasi menghilangkan batas 7 hari, sedangkan verifikasi menghilangkan
peringatan aplikasi belum diverifikasi dan memenuhi kebijakan scope sensitif.
Persyaratan branding seperti homepage, privacy policy, dan authorized domain
ditampilkan oleh konsol saat Anda menekan **Publish app**.

Untuk menghilangkan batas 7 hari:

1. Lengkapi **Branding** dan **Data access**.
2. Di **Audience**, klik **Publish app** dan selesaikan verifikasi yang diminta.
3. Hapus token lama, lalu login ulang agar token baru diterbitkan saat status
   sudah Production. Token lama yang diterbitkan saat Testing tidak berubah
   menjadi token panjang hanya karena status dipublikasikan.

Bila Anda memakai Google Workspace dan hanya mengizinkan pengguna organisasi,
**Internal** dapat menjadi pilihan yang lebih sederhana: alur test user eksternal
dan batas 7 hari untuk External/Testing tidak berlaku. AutoOffice tetap memakai
OAuth user flow pada opsi Internal tersebut. Service account tetap tidak
didukung.

## Referensi

- [CLI AutoOffice](cli.md) untuk target, flag `--sync`, dan kode keluar.
- [Authoring deck](deck-authoring.md) untuk struktur `deck.yaml` dan alur build.
- [Kontrak state Google](../contracts/google-state.md) untuk isi state dan
  kepemilikan file.
- [Troubleshooting](troubleshooting.md) untuk masalah build dan perkakas di luar
  OAuth.

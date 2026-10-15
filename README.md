# Scraping

## Gambaran Umum

Repositori ini berisi kumpulan skrip dan notebook untuk melakukan scraping dari berbagai sumber data, terutama data ulasan produk. Fokus utama repositori ini meliputi:

1. **Berita** – scraping artikel berita.
2. **Twitter (X)** – scraping cuitan menggunakan API pihak ketiga **Apify**.
3. **GMPAS** – scraping ulasan dari platform GMPAS.
4. **Shopee** – scraping ulasan produk dari Shopee.

Setiap alat memiliki kebutuhan tersendiri, seperti API key, cookies, dan konfigurasi lainnya. Petunjuk penggunaan untuk masing-masing alat dijelaskan pada bagian berikut.

## Deskripsi Alat dan Petunjuk Penggunaan

### 1. `berita.ipynb` – Notebook Scraping Berita

- **Tujuan**: Mengambil artikel berita dari sumber berita yang telah ditentukan menggunakan library `scrapling`.
- **Persyaratan**:
  - Python 3.9 atau versi yang lebih baru.
  - Instal dependensi menggunakan `pip install -r requirements.txt`, termasuk library `scrapling`.
  - Tidak memerlukan API key. Notebook mengambil data dari halaman berita yang tersedia secara publik.
- **Cara Menjalankan**:
  1. Buka notebook menggunakan Jupyter (`jupyter notebook berita.ipynb`).
  2. Jalankan setiap sel secara berurutan.
  3. Pada sel terakhir, hasil scraping akan disimpan dalam format JSON/CSV di direktori `data/berita/`.

### 2. `twiter.ipynb` – Notebook Scraping Twitter (X)

- **Tujuan**: Mengambil cuitan berdasarkan kata kunci pencarian atau linimasa pengguna menggunakan API **Apify**.
- **Persyaratan**:
  - Python 3.9 atau versi yang lebih baru.
  - Instal dependensi menggunakan `pip install -r requirements.txt`, termasuk library `apifai`.
  - **API key Apifai**: Daftar melalui [Apify](https://console.apify.com), buat token API, lalu simpan token tersebut dalam file `.env` dengan format `APIFAI_TOKEN=your_token`.
- **Cara Menjalankan**:
  1. Buat file `.env` di direktori utama repositori dan masukkan token API.
  2. Buka notebook `twiter.ipynb` menggunakan Jupyter.
  3. Atur parameter pencarian pada sel pertama, seperti hashtag, nama pengguna, dan rentang tanggal.
  4. Jalankan seluruh sel notebook. Hasil scraping akan disimpan di direktori `data/twitter/`.

### 3. `gmpas.py` – Scraper Ulasan Google Maps

- **Tujuan**: Mengambil informasi satu tempat di Google Maps (nama, kategori, rating, alamat, telepon, website, jam buka, koordinat) beserta ulasan penggunanya, tanpa API. Otomatisasi browser memakai Playwright.
- **Persyaratan**:
  - Python 3.9 atau versi yang lebih baru.
  - Google Chrome terpasang di komputer.
  - Instal dependensi:

```bash
    pip install playwright pandas
    playwright install chromium
```

  - **Sesi login Google (wajib untuk lebih dari ±5 ulasan)**: tanpa login, Google Maps hanya menampilkan beberapa ulasan pertama. Login dilakukan manual satu kali dan tersimpan di folder profil browser (tidak memakai `cookies.json`, dan tidak ada password di kode).
    - Gunakan **akun Google cadangan**, bukan akun utama.
    - Simpan folder profil **di luar OneDrive** (mis. `C:\chrome_profile`) dan jangan di-commit ke Git, karena isinya sesi login.
- **Langkah 1 – Login sekali saja**:

```bash
  py gmpas.py --login --profile C:\chrome_profile --channel chrome
```

  Browser Chrome akan terbuka. Login ke akun Google, lalu kembali ke terminal dan tekan ENTER. Sesi tersimpan di folder profil.

- **Langkah 2 – Menjalankan scraping**:

```bash
  py gmpas.py "<URL_TEMPAT_GOOGLE_MAPS>" --max-reviews 1000 --sort all --profile C:\chrome_profile --channel chrome --headful
```

  Salin URL dari address bar browser saat halaman tempat terbuka (bukan hasil pencarian), dan tulis di dalam tanda kutip. Nama tempat biasa (mis. `"Tugu Yogyakarta"`) juga bisa dipakai sebagai target.

  Keterangan parameter:

  | Parameter | Keterangan |
  |---|---|
  | `target` | URL Google Maps atau nama tempat. |
  | `--profile` | Folder profil browser yang menyimpan sesi login Google. |
  | `--login` | Mode login manual satu kali (dipakai bersama `--profile`). |
  | `--channel` | `chrome` atau `msedge`, memakai browser yang terpasang. Disarankan `chrome`. |
  | `--max-reviews` | (Opsional) Batas jumlah ulasan. Default `1000`. |
  | `--sort` | (Opsional) `Newest`, `Most relevant`, `Highest rating`, `Lowest rating`, atau `all` (ambil dengan 4 urutan lalu gabung tanpa duplikat). Default `Newest`. |
  | `--lang` | (Opsional) Bahasa tampilan Maps: `id` atau `en`. Default `id`. |
  | `--out` | (Opsional) Awalan nama file output. Default `gmaps_output`. |
  | `--headful` | (Opsional) Tampilkan jendela browser. |
  | `--raw-html` | (Opsional) Simpan HTML mentah tiap ulasan untuk parsing ulang. |
  | `--cdp` | (Opsional) Sambung ke Chrome yang sudah berjalan dengan `--remote-debugging-port`, misalnya `http://localhost:9222`. Dipakai jika login lewat `--profile` ditolak Google. |
  | `--debug` | (Opsional) Cetak informasi diagnosis dan simpan screenshot/HTML saat macet. |

- **Hasil (output)**:
  - `gmaps_output.json`: info tempat dan semua ulasan.
  - `gmaps_output_reviews.csv`: ulasan dalam bentuk tabel.
  - `gmaps_output_checkpoint.json`: hasil sementara yang disimpan tiap 200 ulasan.
  - Kolom ulasan: `review_id`, `reviewer_name`, `reviewer_profile_url`, `reviewer_meta`, `is_local_guide`, `rating`, `date_relative`, `text`, `text_displayed`, `is_translated`, `likes`, `details`, `photos`, `owner_response`, `owner_response_date`.

- **Catatan**:
  - Gunakan kolom `text` untuk analisis, karena berisi bahasa asli penulis. `text_displayed` bisa berupa hasil terjemahan otomatis Google.
  - Jumlah ulasan yang didapat bisa lebih sedikit dari total yang tampil di Maps, karena sebagian rating tidak disertai teks.
  - Class CSS Google Maps sering berubah. Jika ada kolom kosong atau scraping macet, jalankan dengan `--headful --debug` dan sesuaikan selector di bagian `SEL` dan `parse_review`.
  - Scraping Google Maps melanggar ketentuan layanan Google. Gunakan hanya untuk keperluan pembelajaran atau riset, dan anonimkan nama serta URL profil reviewer sebelum data dibagikan atau dipublikasikan.

### 4. `shopee.py` – Scraper Ulasan Shopee

- **Tujuan**: Mengambil data ulasan pengguna dari halaman penilaian toko Shopee.
- **Persyaratan**:
  - Python 3.9 atau versi yang lebih baru.
  - Instal dependensi menggunakan `pip install -r requirements.txt`, termasuk library `selenium` dan `webdriver-manager`.
  - **Cookies**: File `cookies.json` diperlukan oleh skrip ini untuk menggunakan sesi browser yang telah terautentikasi. Keberhasilan penggunaannya bergantung pada sesi yang masih berlaku dan mekanisme perlindungan Shopee.
- **Cara Mendapatkan `cookies.json`**:
  1. Instal Selenium dan WebDriver Manager:

     ```bash
     pip install selenium webdriver-manager
     ```

  2. Jalankan skrip bantu yang tersedia di repositori, atau ikuti panduan [Melewati Sistem Auth Website di Selenium, Emang Bisa?](https://fajrulfalah18.medium.com/melewati-sistem-auth-website-di-selenium-emang-bisa-8d88a8a177e8) untuk mengekspor cookies sesi ke file `cookies.json`.

- **Cara Menjalankan**:

  ```bash
  python shopee.py --url <SHOPEE_RATING_URL> --cookies cookies.json --output shopee_reviews.csv
  ```

  Ganti `<SHOPEE_RATING_URL>` dengan URL halaman penilaian Shopee yang telah diperoleh pada bagian [Cara Mendapatkan URL Halaman Ulasan Shopee](#cara-mendapatkan-url-halaman-ulasan-shopee).

  ---

  ## Nomenklatur Dataset

  | Atribut | Deskripsi |
  |-----------|-------------|
  | `nama pengguna` | Nama pengguna yang memberikan ulasan |
  | `produk` | Nama produk dari toko |
  | `review` | Teks ulasan yang ditulis oleh pengguna |
  | `rating` | Nilai rating yang diberikan pada produk |
  | `waktu transaksi` | Waktu pengguna melakukan transaksi |

  ---

  ## Cara Mendapatkan URL Halaman Ulasan Shopee

  1. Buka toko Shopee yang ingin diambil datanya, kemudian masuk ke bagian **Penilaian** atau **Rating**.
  2. Salin URL halaman tersebut. Contoh: `https://shopee.co.id/buyer/#########/rating?shop_id=#########`.
  3. Gunakan URL tersebut sebagai input untuk menjalankan scraper Shopee.

  ---

## Konfigurasi Umum

Ikuti langkah-langkah berikut untuk menyiapkan lingkungan kerja sebelum menjalankan skrip atau notebook.

### 1. Membuat Virtual Environment

```bash
python -m venv env
```

### 2. Mengaktifkan Virtual Environment

- **Windows**:

  ```bash
  .\env\Scripts\activate
  ```

- **Linux/macOS**:

  ```bash
  source env/bin/activate
  ```

### 3. Menginstal Dependensi

Pastikan terminal berada di direktori utama repositori, kemudian jalankan:

```bash
pip install -r requirements.txt
```

### 4. Menjalankan Alat

Jalankan skrip atau notebook yang ingin digunakan sesuai dengan petunjuk pada bagian **Deskripsi Alat dan Petunjuk Penggunaan**.

Pastikan seluruh dependensi telah terinstal dan konfigurasi yang diperlukan, seperti API key atau cookies, telah disiapkan sebelum memulai proses scraping.

---
# Reviews — SustainaBowl

Implementasi Django Templates + AJAX (Fetch), tanpa framework frontend baru. Semua review, rating, dan helpful vote dibaca dari database. Tidak ada seed menu/review untuk database aplikasi.

## Menjalankan lokal

Dari root repository, pada branch `reviews`:

```sh
uv sync
uv run python manage.py migrate
uv run python manage.py tailwind build
uv run python manage.py runserver
```

Buka `http://127.0.0.1:8000/reviews/menu/<menu-key>/`. Sebelum adapter Catalog tersedia, gunakan ID menu yang disepakati tim: halaman hanya menampilkan identitas `Menu <menu-key>` dan tidak mengklaim menu tersebut sudah ada di Catalog. Login memakai Accounts. Pelanggan dapat menulis beberapa review, sesuai state Figma setelah publish yang menampilkan review baru dan review lamanya sekaligus. Tenan dapat membaca, memfilter, dan memberi helpful vote; tombol menulis disembunyikan.

```sh
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test apps.reviews
uv run python manage.py test
uv run ruff check apps/reviews config/urls.py
uv run ruff format --check apps/reviews config/urls.py
```

## Fitur dan aturan

- CRUD review dengan modal create, edit terisi, dan konfirmasi delete. GET tidak menghapus data. Author dan menu ditentukan server, bukan field POST.
- Hanya pelanggan yang sudah login dapat membuat review. Edit/hapus dibatasi pemilik, termasuk melalui URL langsung. CSRF tetap aktif.
- Dua rating integer 1–5: Food Taste dan Sustainable Packaging. Database memiliki check constraints.
- Summary seluruh review menu, tidak berubah ketika filter diterapkan. Overall adalah rata-rata dua skor; distribusi/filter Rating menggunakan Food Taste. Bintang summary dibulatkan ke integer terdekat, angka rata-rata tetap satu desimal.
- Rating; sentimen Positive/Neutral/Negative; packaging satisfaction: 5 Very Satisfied, 4 Satisfied, 3 Neutral, 1–2 Unsatisfied. Filter digabung dengan AND.
- Sentimen menggunakan heuristik kata dalam teks Inggris/Indonesia, dengan negasi sederhana, di `selectors.py`. Bukan prediksi ML atau turunan rating. Teks tanpa kecocokan/netral dianggap Neutral. Heuristik terbatas untuk sarkasme dan kalimat kompleks; penyaringan ini memindai teks review menu sehingga dapat diganti anotasi tersimpan saat volume besar.
- Sort Newest, Oldest, Most Helpful, Highest Rating (Food Taste); tie-break deterministik berdasarkan waktu dan PK.
- Empat review per halaman, Load More menambahkan hasil tanpa reload. URL filter dapat dibuka langsung; backend tetap mendukung pagination biasa.
- Satu helpful vote per akun/review dengan unique constraint. Tombol kedua kali membatalkan vote, dan state terpilih berasal dari database. Row lock digunakan saat toggle.
- Satu foto opsional: JPEG/PNG asli, maksimum 5 MiB, divalidasi Pillow serta ekstensi. Nama storage menggunakan UUID. Foto dapat diganti/dihapus; file lama dibersihkan setelah transaksi berhasil. Preview dan counter 500 karakter tersedia.
- Empty reviews, no matching reviews, active chips, skeleton loading, request error/retry, submitting/saving/deleting, guest login prompt, dan notifikasi publish/update/delete.
- Dialog native menyediakan focus trap dan Escape. Fokus kembali ke kontrol sebelumnya. HTML meng-escape teks pengguna.

## Kontrak Catalog (menunggu model tim)

`apps/catalog/models.py` kosong saat implementasi. Tidak dibuat model/FK Catalog baru. `Review.menu_key` merupakan referensi opaque berupa slug, maksimum 100 karakter; bukan foreign key dan belum menjamin keberadaan menu tanpa resolver. Integrasi produksi harus memasang resolver untuk validasi keberadaan menu dan metadata asli.

Setting opsional:

```python
REVIEWS_MENU_RESOLVER = "apps.catalog.integrations.resolve_review_menu"
```

Callable `resolve_review_menu(key: str)` mengembalikan `apps.reviews.integration.MenuContext`, atau `None`/raise `Http404` bila tidak ditemukan. `MenuContext.key` harus sama dengan key yang diminta. Fields: `key`, `name`, `tenant`, `description`, `image_url`, `detail_url`, `packaging_label`. Field opsional kosong tidak dirender. Gunakan URL tepercaya untuk gambar dan detail. File adapter di Catalog belum dibuat karena modelnya belum disepakati.

Dari halaman detail Catalog:

```django
{% url 'reviews:menu' menu_key=menu.pk %}
```

Tim perlu menyepakati jenis PK/slug stabil (termasuk UUID yang dapat dikonversi ke string), kebijakan menu terhapus, dan migrasi pemetaan ke FK ketika model final tersedia. Tidak ada perubahan atau migrasi pada Catalog dalam pekerjaan ini.

## Kontrak Orders / kemasan (opsional)

Badge pada kartu adalah snapshot `Review.packaging_type`: `reusable`, `compostable`, atau kosong. Figma tidak memiliki input pilihan jenis kemasan pada form review, jadi nilai ini tidak diterima dari browser.

```python
REVIEWS_PACKAGING_RESOLVER = "apps.orders.integrations.resolve_review_packaging"
```

Callable `resolve_review_packaging(menu_key, user)` mengembalikan salah satu nilai tersebut dari pesanan/kemasan asli pelanggan. Dipanggil saat create; edit tidak mengganti snapshot. Tanpa adapter, badge tidak ditampilkan. Tim Orders perlu menyepakati cara memilih pesanan jika pelanggan membeli menu yang sama beberapa kali. Belum ada klaim verified purchase, pembatasan wajib membeli, atau relasi Order karena kontraknya belum tersedia.

## Integrasi Accounts

FK memakai `settings.AUTH_USER_MODEL`, `CustomUser.is_customer`, dan `display_name` yang sudah ada. Login prompt mengarah ke `accounts:login` dengan `next` kembali ke menu Reviews. Tidak ada perubahan Accounts. Header/footer/tombol/form styles dan toast script yang tersedia digunakan kembali. Styling tambahan terbatas pada Reviews.

## Routes

| Method | URL relatif terhadap /reviews/ | Nama |
| --- | --- | --- |
| GET | menu/<menu-key>/ | reviews:menu |
| GET, POST | menu/<menu-key>/create/ | reviews:create |
| GET, POST | <pk>/edit/ | reviews:edit |
| GET, POST | <pk>/delete/ | reviews:delete |
| POST | <pk>/helpful/ | reviews:helpful |

Header `X-Reviews-Request: true` memilih partial HTML untuk daftar/form dan JSON untuk mutasi berhasil. Form tidak valid: HTTP 422 dan form dengan errors; guest AJAX: 401; bukan pemilik: 404; akun tenan membuat review: 403; filter tidak valid: 400. Tanpa header, mutasi berhasil redirect dan memakai Django messages. Server/network error ditangani client dengan retry tanpa menampilkan detail internal.

## Migration dan file

- `models.py`: Review, HelpfulVote, constraints dan index.
- `migrations/0001_initial.py`: tabel Reviews dan helpful votes, FK Accounts, constraints/index.
- `migrations/0002_review_packaging_type.py`: snapshot jenis kemasan opsional. Keduanya aditif dan sudah diterapkan lokal.
- `forms.py`: validasi input/upload dan pilihan filter.
- `selectors.py`: query, summary, filter/sort, sentimen.
- `integration.py`: adapter Catalog dan Orders.
- `views.py`, `urls.py`: endpoint HTML/AJAX, izin, CRUD dan votes.
- `admin.py`: registrasi model Reviews.
- `templatetags/__init__.py`, `templatetags/review_tags.py`: pemilihan aset bintang.
- `templates/reviews/reviews.html`, `modal_base.html`, `form.html`, `delete.html`, `filter_error.html`, `partials/results.html`, `partials/card.html`.
- `static/reviews/reviews.css`, `reviews.js`, `stars-0.svg` sampai `stars-5.svg`. SVG bintang diunduh langsung dari Figma MCP, ukuran asli 116 × 20 dipertahankan. Ikon lain memakai Lucide yang sudah tersedia.
- `tests.py`: 16 tes Reviews.
- `README.md`: dokumentasi ini.
- Integrasi di luar app: satu include `reviews/` pada `config/urls.py`. CSS Tailwind dibangun ulang ke output yang sudah di-ignore Git; sumber Design System tidak diubah.

## Verifikasi, 24 Oktober 2026

- Django system checks: lulus, 0 masalah.
- Makemigrations dry-run: tidak ada perubahan model yang belum dimigrasikan.
- Migrations Reviews: dibuat, diperiksa, diterapkan; hanya create/add operasi, tanpa operasi destruktif.
- Seluruh suite: 56 tes lulus (16 Reviews, 40 tes modul yang sudah ada). Meliputi CRUD, isolasi menu, auth/owner, guest/tenan, CSRF, escape XSS, batas rating database, helpful unique/toggle, validasi teks/foto, file cleanup, kombinasi filter, sort, pagination, serta kontrak adapter.
- Ruff check/format dan build Tailwind: lulus.
- Ada warning lingkungan Whitenoise bahwa folder `staticfiles/` belum ada selama tes; tidak menggagalkan tes. Folder tersebut dibuat lewat collectstatic saat deployment, bukan dibutuhkan oleh dev server.
- Browser QA memakai database SQLite temporer terpisah; fixture pengujian tidak masuk ke database project. Hasil pemeriksaan browser akhir dicatat di bawah.

## Referensi Figma

Sumber: [SustainaBowl Reviews](https://www.figma.com/design/jlTevWxK0uS15Kw4UGy6iW/SustainaBowl-Modules?node-id=150-514). Metadata, design context, dan screenshot seluruh frame Reviews diperoleh melalui Figma MCP. Design System page 9:2 juga diperiksa, termasuk fonts, sizes, colors, buttons, input, toast, dan dropdown. Tidak ada perubahan Figma.

Target styling: content desktop max-width 1120, latar #f4f7f2, surface putih, border #d7dfd9, brand #2a835f, accent #12544f, teks #092328, secondary #63706c, Poppins Bold/Inter Regular-Semibold, radius kartu 10, modal 16, jarak utama 24/32, tombol tinggi 44. Breakpoint tablet/mobile ditambahkan mengikuti layout fleksibel karena frame Reviews yang tersedia berukuran desktop.

Batas kesesuaian: header/footer menggunakan implementasi bersama repository sebagaimana diminta; tidak dirombak untuk menyalin perbedaan shell Figma. Menu/tenant/foto/badge diisi data integrasi nyata, sehingga belum bisa dibandingkan dengan contoh nama makanan dalam desain. Dropdown menggunakan select native untuk aksesibilitas; popup mengikuti platform. Notifikasi memakai toast bersama. Belum ada klaim pixel-perfect untuk seluruh viewport/platform atau hasil screenshot otomatis.

Frame yang dibaca:

| Node | Frame |
| --- | --- |
| 156:819 | Menu Detail — Customer Reviews |
| 169:4750 | Reviews — Prototype Guide |
| 157:1140 | Create Review — Default |
| 157:1192 | Create Review — Selected Ratings |
| 157:1256 | Create Review — Photo Uploaded |
| 157:1308 | Create Review — Validation Error |
| 157:1360 | Create Review — Submitting |
| 157:1455 | Create Review — Server Error |
| 157:1507 | Edit Review — Prefilled |
| 157:1576 | Delete Review — Confirmation |
| 157:1588 | Guest — Log in to continue |
| 164:4175 | Create Review — Photo Removed |
| 164:4237 | Edit Review — Saving Changes |
| 164:4297 | Delete Review — Deleting |
| 161:1532 | Menu Detail — Guest Reviews |
| 161:1977 | Menu Detail — No Reviews Yet |
| 161:2349 | Menu Detail — No Matching Reviews |
| 161:2751 | Menu Detail — Filtering and Loading |
| 161:3167 | Menu Detail — Review Published |
| 161:3595 | Menu Detail — Request Error |
| 161:3968 | Menu Detail — Review Deleted |
| 161:4339 | Menu Detail — Review Updated |
| 162:3585 | Menu Detail — Positive Reviews and Active Filters |
| 162:3962 | Menu Detail — Sorted by Most Helpful |
| 164:4309 | Menu Detail — Helpful Vote Selected |
| 152:524 | Reviews / Primary Button |
| 152:535 | Reviews / Secondary Button |
| 152:585 | Reviews / Star Rating |
| 152:598 | Reviews / Helpful Button |
| 152:605 | Reviews / Filter Chip |
| 152:630 | Reviews / Filter Dropdown |
| 152:656 | Reviews / Image Upload |
| 152:681 | Reviews / Toast |
| 155:796 | Reviews / Review Card |
| 155:1059 | Reviews / Review Form |
| 155:1167 | Reviews / Modal |
| 155:1193 | Reviews / Empty State |
| 162:3534 | Reviews / Filter Option |
| 162:3535 | Rating — Dropdown Options |
| 162:3550 | Sentiment — Dropdown Options |
| 162:3561 | Sustainable Packaging Satisfaction — Dropdown Options |
| 162:3574 | Sort — Dropdown Options |
| 162:4327 | Reviews — Component States Showcase |


### Hasil browser QA akhir

- Login Accounts kembali ke halaman Reviews melalui `next`.
- Guest: empty state dan modal Log in to continue terlihat.
- Publish: dua rating dan teks tersimpan; modal tertutup; toast sukses muncul; jumlah judul dan summary berubah 6 → 7.
- Edit: form memuat nilai tersimpan, teks/rating berubah, summary diperbarui, toast updated muncul tanpa request-error.
- Delete: konfirmasi terlihat; fixture review QA dihapus; jumlah judul dan summary kembali 7 → 6; toast deleted muncul.
- Helpful: angka 0 → 1 dan state selected langsung berubah.
- Load More: empat kartu menjadi enam kartu tanpa reload.
- Filter Rating + Positive: chip aktif dan No reviews match your filters tampil; URL query ikut berubah.
- Tampilan diperiksa pada viewport browser sekitar 654 px; modal scrollable dan filter dua kolom. Breakpoint desktop/ponsel lain belum diuji visual satu per satu.
- Foto, izin, validasi, dan file cleanup diuji pada suite Django. Dialog pemilihan file OS, kegagalan jaringan buatan, dan screenshot regression otomatis belum diuji browser.

Perubahan dibatasi app Reviews dan satu include URL. Branch tetap `reviews`; tidak ada commit, push, merge, PR, perubahan `.env`, atau perubahan desain Figma.

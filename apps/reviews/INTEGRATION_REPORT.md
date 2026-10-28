# Finalisasi Reviews × Orders — 28 Oktober 2026

## Hasil dan kesiapan

Integrasi Catalog, Accounts, dan Orders selesai untuk scope requirement aktual dan siap diajukan sebagai **calon PR untuk review tim**. Tidak ada PR, commit, push, atau merge yang dilakukan. Branch tetap `reviews`, dimulai dari HEAD `24fc545` yang sudah berisi merge Orders PR #9. Kesiapan ini tidak berarti full suite/CI repository sudah hijau atau semua kondisi production sudah diverifikasi.

Kode dan requirement lokal dibaca terlebih dahulu: README utama, README Reviews, model/view/service/template/test Orders dan Reviews, model Catalog/Accounts, setting, serta konfigurasi CI. Sebelum perubahan, seluruh **29 tests Reviews lulus**. Tidak ada AGENTS.md pada direktori project atau direktori induknya.

## Perubahan file

| File relatif repository | Perubahan dan alasan |
| --- | --- |
| `apps/reviews/integration.py` | Resolver Orders aktual: relasi pembeli–order–item–UUID menu, status delivered, pilihan order eksplisit, penanganan riwayat kemasan yang ambigu, validasi nilai adapter. |
| `config/settings.py` | Mengaktifkan `REVIEWS_PACKAGING_RESOLVER = "apps.reviews.integration.order_packaging"`. |
| `apps/reviews/views.py` | Memvalidasi konteks order saat GET halaman/form dan POST; menjaga atribusi session/menu/packaging; mempertahankan konteks pada filter/pagination dan create URL. |
| `apps/reviews/templates/reviews/reviews.html` | Create URL server, ID order tervalidasi, flag pembukaan modal, login next dengan query string. |
| `apps/reviews/templates/reviews/form.html` | Menampilkan menu, kode order, dan kemasan terpilih agar user mengetahui konteks review. |
| `apps/reviews/templates/reviews/partials/results.html` | Konteks order pada form filter dan clear filters. |
| `apps/reviews/static/reviews/reviews.js` | Membuka modal lama dari Orders, mempertahankan order pada AJAX/filter/sort/clear/pagination, menghapus flag pembukaan pada pemuatan hasil. |
| `apps/reviews/tests.py` | Mempertahankan 29 tests awal dan menambah 25 tests integrasi. |
| `apps/orders/templates/orders/partials/order_card.html` | Tautan Write a review untuk setiap item menu delivered yang masih ada, membawa UUID menu dan order. Ini diperlukan karena satu tautan lama hanya memilih item pertama. Kelas tombol lama dipakai kembali. |
| `apps/orders/views.py` | Menghapus `_review_url`, penugasan `order.review_url`, dan import yang sudah tidak dipakai setelah tautan dibentuk per item pada template bersama HTML/AJAX. Tidak mengubah model, checkout, service, API, stok, poin, atau aturan status Orders. |
| `apps/reviews/README.md` | Mengganti kontrak Orders yang belum tersedia dengan implementasi aktif dan kebijakan aktual. Catatan QA 26 Oktober diberi label historis. |
| `apps/reviews/INTEGRATION_REPORT.md` | Laporan ini. |

Tidak ada perubahan CSS, Figma, model Catalog/Accounts/Orders/Reviews, atau migration. Tidak ada redesign; penempatan link per item diperlukan agar pilihan menu tidak ambigu.

## Aturan atribusi dan akses

Requirement Reviews tidak mewajibkan pembelian atau membatasi jumlah review per menu/order. Perilaku itu dipertahankan. Kebijakan delivered mengikuti kondisi tombol review Orders sebelum integrasi. Aturan ini membatasi atribusi label kemasan, bukan melarang customer tanpa pembelian menulis review.

| Kondisi | Hasil |
| --- | --- |
| Order eksplisit milik customer session, delivered, mempunyai OrderItem dengan UUID menu yang tepat | Kemasan dari Order tersebut; pesanan lama juga bisa dipilih meskipun ada pembelian baru. |
| Order eksplisit milik akun lain, berbeda menu, bukan delivered, hilang, kosong, atau malformed | 404; tidak berpindah diam-diam ke order lain. Halaman berkonteks order memerlukan autentikasi customer. |
| Tanpa order eksplisit dan seluruh delivered purchases untuk menu mempunyai satu jenis kemasan | Snapshot jenis tersebut; banyak order/item duplikat tidak mengubah hasil. |
| Tanpa order eksplisit dan riwayat delivered mempunyai reusable sekaligus compostable | Label kosong; tidak memilih berdasarkan tanggal secara spekulatif. Pilih pesanan melalui Orders untuk atribusi spesifik. |
| Tidak pernah membeli, hanya mempunyai cancelled/pending/processing/on_the_way orders | Review tetap dapat dibuat dengan rating kemasan; badge jenis kemasan kosong. |
| Menu dihapus | OrderItem tetap ada dengan menu NULL dan nama historis; link review disembunyikan untuk item itu. Menu aktif lain dalam order tetap mempunyai link. Review orphan tetap tersimpan; pemilik tetap dapat menghapus. |
| Review diedit, order kemudian dihapus, atau wadah reusable dikembalikan | Snapshot kemasan pada review tidak berubah. |

Pencocokan selalu melalui `Order.user` dan `OrderItem.menu_item_id`; nama, harga, tenant, cart, dan field POST tidak dipercaya untuk atribusi. Daftar review publik tetap per menu. Kode/alamat order asing tidak muncul pada respons yang diuji. Alamat order milik sendiri juga tidak dirender dalam halaman/form Reviews. Proteksi owner, customer/tenant, CSRF, rating, foto, helpful votes, dan UUID canonical tetap melalui implementasi Reviews yang sudah ada.

## Verifikasi otomatis

Semua perintah berikut benar-benar dijalankan memakai `.venv/bin/python`, `.venv/bin/ruff`, serta Node lokal; tidak dilakukan sinkronisasi dependency atau perubahan `.env`.

| Pemeriksaan | Hasil akhir |
| --- | --- |
| `python manage.py check` | Lulus, tanpa system-check issue. |
| `python manage.py makemigrations --check --dry-run` | Lulus, No changes detected. |
| `python manage.py migrate --check` | Lulus; tidak ada migration tertunda. Perintah ini tidak menerapkan migration. |
| `python manage.py test apps.reviews --noinput` | **54/54 lulus**: 29 awal + 25 integrasi. |
| `python manage.py test --noinput` | **190/191 lulus**; satu kegagalan lama Design System di bawah. Seluruh 45 tests Orders lulus sebagai bagian suite ini. |
| `ruff check apps/reviews apps/orders/views.py config/settings.py` | Lulus. |
| `ruff format --check apps/reviews apps/orders/views.py config/settings.py` | Lulus, 18 file sudah sesuai. |
| `ruff check .` | 6 temuan lama Catalog, tidak ada temuan baru. |
| `ruff format --check .` | 12 file lama perlu format, tidak ada file perubahan ini yang perlu format. |
| `python manage.py tailwind build` | Lulus, Tailwind CSS v4.3.0. Output CSS berada di direktori yang di-ignore Git. |
| `node --check apps/reviews/static/reviews/reviews.js` | Lulus. |
| `git diff --check` | Lulus. |

Tests baru mencakup kedua kemasan, seluruh status Order, hubungan checkout nyata (`Cart` → `Order`/`OrderItem` → `MenuItem`), tanpa pembelian, pemilik lain, menu berbeda dengan nama/harga sama, invalid/missing order, pembelian berulang, riwayat ambigu, order lama terpilih, multi-menu, 422/AJAX, perubahan kepemilikan/status antara GET dan POST, spoofing POST, snapshot ketika edit/hapus order, menu terhapus sebagian/seluruhnya, guest/tenant, nilai kemasan rusak, wadah dikembalikan, kartu HTML/AJAX, pembukaan modal, serta konteks filter/pagination. Tests lama tetap meliputi CRUD, foto/cleanup, rating, filters, sorting, pagination, votes, permissions, CSRF, escaping, dan query N+1.

## Kegagalan lama di luar Reviews

Baseline dibuat dari `git archive HEAD` ke direktori sementara yang terpisah, tanpa menyalin `.env`/database atau mengubah checkout. Full suite baseline: **165/166 lulus**, dengan kegagalan identik pada `apps.designsystem.tests.DesignSystemPageTests.test_page_is_public_and_uses_application_shell` (`apps/designsystem/tests.py:17`), yang mengharapkan `href="/#manfaat"` sedangkan header memakai `/catalog/`. Tidak diperbaiki dalam scope Reviews.

Ruff baseline dan hasil akhir sama: I001 pada `apps/catalog/admin.py`, `forms.py`, `models.py`, `views.py`; F401 pada `admin.py` (UserAdmin) dan `views.py` (JsonResponse). Format baseline dan akhir sama: migration Accounts 0004; Catalog admin/apps/forms/models/urls/views serta migrations 0001–0005. Tidak dilakukan auto-fix di luar scope.

Django test runner mengeluarkan warning direktori `staticfiles/` belum ada. Build berhasil; `collectstatic` tidak dijalankan sebagai bagian integrasi. Pesan Nominatim 503/down berasal dari skenario mock Map, bukan test yang gagal.

## Browser QA

Server loopback terpisah memakai database dan media di direktori sementara; tidak memakai database aplikasi. Pada viewport sekitar 654 px, login dengan akun QA buatan, buka Orders berisi dua menu dan dua delivered orders (reusable dan compostable):

- Link menu kedua pada pesanan reusable yang lebih lama membuka halaman menu kedua dan modal existing; nama menu, kode pesanan, serta label reusable benar.
- Submit AJAX menyimpan review, menutup modal, memperbarui hasil, dan menampilkan toast serta badge reusable.
- Menu yang sama dari pesanan compostable membuka konteks baru dan menyimpan badge compostable. Kedua review tampil bersamaan dengan label masing-masing.
- Membuka ulang modal mempertahankan order yang dipilih; Cancel menutup modal tanpa membuat review. Helpful berubah 0 → 1.

Screenshot bukti QA disimpan di `/tmp/pts-reviews-orders-browser-qa.png`. Pengujian browser ini manual, bukan screenshot regression otomatis. Semua viewport, upload melalui dialog file OS, network failure/retry, browser lintas platform, dan konkurensi PostgreSQL belum diuji ulang lewat browser pada finalisasi ini. Upload/replace/remove foto dan fitur lama tetap diverifikasi oleh tests backend. Server QA dihentikan setelah pemeriksaan.

## Keterbatasan dan risiko tersisa

- `Review.menu_key` masih string UUID untuk mempertahankan data lama. Tidak ada foreign-key constraint ke menu; jendela race terhadap penghapusan menu tetap mungkin, sebagaimana batas implementasi sebelumnya.
- `packaging_type` adalah snapshot saat create. ID/FK order asal belum disimpan pada Review, tidak ada verified-purchase badge, deduplikasi review per order, atau backfill review lama. Audit ulang sumber order per review memerlukan perubahan skema yang disepakati tim.
- Atribusi dilakukan dari data Orders saat request, bukan constraint database lintas tabel. Perubahan admin atau script yang bersamaan dapat mengubah order setelah dibaca. Tests memverifikasi revalidasi GET → POST, bukan serialisasi semua transaksi paralel. SQLite tidak memberi row lock setara PostgreSQL; deployment PostgreSQL belum diuji dalam finalisasi ini.
- Model Orders belum mempunyai `delivered_at`; tanggal create/update tidak digunakan untuk menebak pesanan mana yang direview. Riwayat kemasan berbeda sengaja membutuhkan order eksplisit. Tim dapat menyepakati aturan produk lain kemudian, tetapi tidak disisipkan asumsi pembelian terbaru.
- Nilai kemasan unsupported dari adapter menyebabkan configuration error dan tidak disimpan pada Review. Perbaikan data Orders yang korup berada di luar scope dan tidak dilakukan otomatis.
- Mekanisme foto, heuristik sentiment, cleanup storage, dan batas skala/query tetap seperti dokumentasi sebelumnya. Tidak ada garbage collector file atau perubahan algoritma sentiment.
- Pipeline repository belum dapat dinyatakan hijau karena kegagalan baseline yang terpisah di atas. Pengujian end-to-end otomatis browser dan deployment tidak ditambahkan atau diklaim lulus.

Database aplikasi tidak di-reset, di-flush, di-seed, atau dihapus. Hash database aplikasi sebelum dan sesudah browser QA sama. `.env`, identitas Git, Figma, dan data aplikasi tidak diubah; tidak ditambahkan co-author. Tidak mengulang merge yang sudah selesai.

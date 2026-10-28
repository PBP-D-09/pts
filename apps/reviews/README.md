# Reviews — SustainaBowl

Modul Django Templates + AJAX (Fetch), menggunakan database Django, Accounts, Catalog, dan Orders asli. Branch kerja `reviews`. Tidak ada framework frontend tambahan.

**Status terbaru (28 Oktober 2026):** integrasi Orders aktif; 54 tests Reviews lulus. Detail perubahan, kebijakan, baseline, dan keterbatasan tersedia di [laporan integrasi Orders](INTEGRATION_REPORT.md). Laporan QA 26 Oktober di bawah dipertahankan sebagai catatan historis.

## Menjalankan

```sh
uv sync
uv run python manage.py migrate
uv run python manage.py tailwind build
uv run python manage.py runserver
```

Buka Catalog → tenant → **Read Reviews** pada kartu menu. Tautan tersedia pada bagian All items dan kategori. Halaman dapat dibuka langsung di `/reviews/menu/<MenuItem UUID>/`.

Catalog belum mempunyai halaman detail menu tersendiri. Reviews menampilkan konteks menu dan breadcrumb kembali ke halaman tenant; menu tanpa tenant kembali ke Catalog. Tidak dibuat halaman detail Catalog baru.

Database lokal saat audit 26 Oktober 2026 memiliki **0 menu dan 0 review**. Tidak ditambahkan seed ke database aplikasi. Pengujian membuat MenuItem asli di database test / database browser QA sementara.

## Integrasi Catalog dan strategi data lama

Setting wajib (sudah terdaftar dalam `config/settings.py`):

```python
REVIEWS_MENU_RESOLVER = "apps.reviews.integration.catalog_menu"
```

Resolver melakukan satu query `MenuItem.select_related("tenantId")` dan mengembalikan `MenuContext` dengan:

| Field | Sumber |
| --- | --- |
| key | `str(MenuItem.pk)` dalam format UUID canonical lowercase dengan tanda hubung |
| name | `MenuItem.name` |
| description | `MenuItem.description` |
| tenant | `MenuItem.tenantId.name`, atau kosong jika tenant null |
| image_url | `MenuItem.photo.url`, atau kosong jika tidak ada foto |
| detail_url | Halaman Catalog tenant, atau Catalog utama jika tenant null |

Tidak ada fallback `Menu contoh-menu`. UUID tidak ditemukan, slug lama, UUID uppercase/noncanonical, dan identifier tidak valid menghasilkan 404. Setting resolver yang hilang menghasilkan configuration error agar tidak menerima menu fiktif. Foto menu bersifat dinamis; foto review disimpan terpisah.

`Review.menu_key` tetap `SlugField(max_length=100)`: UUID canonical sepanjang 36 karakter valid untuk field ini. Tidak ada perubahan skema, migration baru, pemetaan heuristik, atau penghapusan data. Ini mempertahankan baris lama tanpa memaksakan FK yang akan menolak identifier lama.

Keberadaan menu divalidasi oleh resolver pada halaman, create, edit, dan helpful. Create menggunakan key hasil resolver dan author dari session; field POST tidak dapat mengganti keduanya. `Review.clean()` juga menolak key tidak valid pada admin / `full_clean()`. Seperti Django pada umumnya, `save()`, `bulk_create()`, dan `QuerySet.update()` tidak otomatis menjalankan `full_clean()`: pemanggil ORM/script baru harus melakukan validasi sendiri. String reference tidak menyediakan foreign key constraint atau jaminan terhadap penghapusan Catalog secara bersamaan. FK nullable dan backfill terverifikasi dapat dipertimbangkan tim kemudian jika membutuhkan integritas lintas tabel di tingkat database.

Kebijakan menu terhapus / identifier lama:

- Review, vote, dan foto lama **tidak dihapus otomatis** oleh penghapusan menu/tenant Catalog.
- Halaman menu, create, edit, dan helpful menghasilkan 404; data tidak tercampur dengan menu aktif.
- Pemilik masih boleh menghapus review melalui URL delete miliknya. Konfirmasi/back link dan respons sukses kembali ke Catalog bila menu tidak tersedia. Akun lain tetap ditolak.
- Baris lama dapat diaudit melalui admin/database oleh maintainer. Jika ada pemetaan historis yang dapat dibuktikan, backfill `menu_key` ke UUID canonical melalui migration/script yang direview, dengan backup dan dry-run. Jangan menebak pemetaan dari kesamaan nama atau menghapus baris tanpa pemetaan.
- Mengedit baris orphan melalui admin memerlukan key menu yang valid. Membuka admin tidak mengubah data lama.

## Fitur dan aturan

- Create/read/edit/delete, modal terisi saat edit, konfirmasi delete. GET delete tidak menghapus.
- Hanya customer terautentikasi dapat create/edit. Pemilik saja dapat edit/delete; pemilik yang jenis akunnya berubah masih dapat menghapus datanya. Tenant dapat membaca/filter/vote; tidak dapat menulis review baru atau mengedit review customer.
- CSRF aktif untuk semua mutation. Guest AJAX menerima 401 dan modal login; request biasa redirect ke Accounts. `next` kembali ke Reviews; Accounts tetap memvalidasi redirect.
- Food Taste dan Sustainable Packaging integer 1–5, dengan validator form dan check constraints database.
- Summary menghitung seluruh review **menu terkait**, terlepas dari filter. Overall = rata-rata kedua skor; distribusi, filter Rating, dan Highest Rating menggunakan Food Taste. Bintang dibulatkan ke integer terdekat; skor tampil satu desimal.
- Filter rating, sentiment, packaging satisfaction digabung dengan AND. Packaging: 5 Very Satisfied, 4 Satisfied, 3 Neutral, 1–2 Unsatisfied.
- Sentiment memakai heuristik kata Inggris/Indonesia dan negasi sederhana (`selectors.py`), bukan ML/verified opinion. Sarkasme dan kalimat kompleks terbatas. Filter ini memindai teks review menu; pertimbangkan hasil tersimpan bila volume besar.
- Newest, Oldest, Most Helpful, Highest Rating; tie-break waktu/PK deterministik. Pagination empat kartu; Load More menambah hasil tanpa reload.
- Helpful toggle / cancellation; unique constraint akun+review, row lock pada backend yang mendukungnya. SQLite lokal tidak menyediakan row lock setara PostgreSQL.
- Foto review JPEG/PNG asli maksimum 5 MiB, diperiksa Pillow dan ekstensi. UUID storage name, replace/remove; file lama dihapus setelah commit. Callback cleanup memakai `robust=True`: kegagalan storage dicatat Django tanpa mengubah respons sukses menjadi error setelah data sudah tersimpan. File tersisa akibat storage gagal perlu cleanup operasional; tidak ada garbage collector otomatis.
- Edit/delete memakai transaksi dan lock review agar request bersamaan tidak memakai state foto lama yang berbeda pada database yang mendukung row lock.
- Author dan tenant author diambil melalui join; helpful count dan status vote dianotasi sehingga tidak ada query per kartu.
- Empty, no matching, active filters, loading, request error/retry, publish/update/delete toast, selected helpful. Native dialog menyediakan focus trap/Escape; teks pengguna di-escape.

## Integrasi Orders (aktif)

```python
REVIEWS_PACKAGING_RESOLVER = "apps.reviews.integration.order_packaging"
```

Adapter ada di modul Reviews agar implementasi bisnis Orders tidak perlu diubah. `order_packaging(menu_key, user, *, order_id=None)` mengembalikan `"reusable"`, `"compostable"`, atau `""`. Wrapper `resolve_packaging` tetap memvalidasi nilai; hasil lain menghasilkan configuration error. Adapter dua argumen lama tetap dapat dipakai untuk pemanggilan tanpa order eksplisit; adapter pengganti yang mendukung alur Orders wajib menerima keyword `order_id`. Setting kosong tetap menghasilkan snapshot kosong, tanpa menerima klaim kemasan dari browser.

Sumber relasi: `Order.user` → customer terautentikasi, `Order.items` → `OrderItem.menu_item_id` → UUID `MenuItem`, dan `Order.packaging_type`. Nama menu, harga, tenant penjual, Cart, serta field POST tidak dijadikan bukti pembelian. Guest dan tenant tidak memperoleh kemasan melalui adapter ini.

Aturan berdasarkan requirement Reviews dan perilaku Orders aktual:

- Reviews tetap boleh dibuat tanpa pembelian: requirement tidak mensyaratkan verified purchase. Tidak ada pembatasan baru satu review per menu/order.
- Hanya `delivered` digunakan untuk atribusi kemasan, mengikuti tombol review yang sudah tersedia pada status itu di Orders. `pending`, `processing`, `on_the_way`, dan `cancelled` diabaikan pada pencarian otomatis; pilihan eksplisit ke status tersebut menghasilkan 404. Ini aturan integrasi yang diturunkan dari implementasi Orders, bukan klaim adanya requirement delivered-only untuk seluruh CRUD Reviews.
- Orders menampilkan **Write a review per item menu yang masih ada**. Tautan `/reviews/menu/<uuid>/?order=<order-uuid>&write=1` membuka menu yang tepat dan modal lama. Bukan lagi memilih item pertama. Kondisi status dan menu pada kartu HTML/AJAX memakai template yang sama; kelas visual yang ada dipakai ulang, tanpa CSS atau perubahan Figma.
- Order eksplisit divalidasi saat membuka halaman, membuka form, dan submit. Harus milik customer session, delivered, dan mengandung UUID menu tersebut. ID kosong, salah format, tidak ditemukan, milik orang lain, atau menu tidak cocok → 404 tanpa fallback ke order lain. Parameter POST `order`, `order_id`, author, menu, dan kemasan tidak mengganti konteks URL/session.
- Tanpa order eksplisit (misalnya dari Catalog), ambil jenis kemasan berbeda dari semua delivered orders milik user untuk menu itu. Satu jenis → snapshot jenis itu, termasuk bila ada beberapa pembelian. Tidak ada pembelian atau reusable dan compostable sama-sama ada → snapshot kosong; jangan menebak pembelian terbaru. User dapat memilih order yang tepat melalui Orders. Tidak digunakan `created_at`/`updated_at` sebagai tanggal delivered karena model tidak menyimpan `delivered_at`.
- Konteks order dipertahankan saat filter, sort, pagination, clear filters, error form 422, login redirect, dan submit AJAX. Flag `write` dihapus pada hasil/filter/pagination agar modal tidak terbuka ulang. Form menampilkan nama menu, kode order, dan kemasan; alamat dan rincian pribadi pesanan tidak dirender.
- Snapshot `packaging_type` diambil hanya saat create dan tidak berubah saat edit, order dihapus, atau wadah dikembalikan. Tidak ada backfill label pada review lama.
- `OrderItem.menu_item` memakai SET_NULL saat menu dihapus. Baris itu tetap tampil dalam riwayat dengan snapshot nama, tetapi tidak mempunyai tautan review. Menu bernama sama tidak digunakan sebagai pengganti. Review lama tetap tersimpan dan dapat dihapus oleh pemilik sesuai kebijakan orphan Catalog di atas.

Skema tetap: `Review` menyimpan UUID menu sebagai string dan jenis kemasan sebagai snapshot, **belum menyimpan FK/ID order asal**. Karena itu badge bukan bukti verified purchase yang dapat diaudit ulang per review. Tidak ada migration atau perubahan database aplikasi untuk integrasi ini. Lihat risiko konkurensi, penyimpanan foto, dan batas verifikasi dalam laporan terbaru.

## Routes

| Method | URL relatif terhadap /reviews/ | Nama |
| --- | --- | --- |
| GET | menu/<menu-key>/ | reviews:menu |
| GET, POST | menu/<menu-key>/create/ | reviews:create |
| GET, POST | <pk>/edit/ | reviews:edit |
| GET, POST | <pk>/delete/ | reviews:delete |
| POST | <pk>/helpful/ | reviews:helpful |

## Referensi Figma dan batas visual

Sumber: [SustainaBowl Reviews](https://www.figma.com/design/jlTevWxK0uS15Kw4UGy6iW/SustainaBowl-Modules?node-id=150-514).

Pada audit ini Figma MCP berhasil membaca struktur Reviews (150:514), design context + screenshot MAIN (156:819), MODALS/create (157:1140), STATES/request error (161:3595), dan COMPONENTS/showcase (162:4327). Design System (9:2) dibaca melalui metadata dan context Fonts: Heading (10:8), Sub-heading (10:11), Body (10:15). Pembacaan context tingkat page sempat gagal karena selection; pembacaan frame langsung berhasil. Tidak ada perubahan file Figma.

UI lama dipertahankan: max-width 1120, brand #2a835f, accent #12544f, teks #092328, secondary #63706c, border #d7dfd9, Poppins Bold / Inter, kartu radius 10, modal 16, jarak 24/32, tombol tinggi 44. Shared shell, button, panel, typography, icon Lucide, toast, dan SVG bintang lokal tetap digunakan. Foto menu kini mengikuti data Catalog.

Browser inspeksi dilakukan pada viewport sekitar 654 px: filter dua kolom, modal scrollable, context menu/foto dan state utama terbaca. Tidak mengklaim pixel-perfect semua viewport atau screenshot regression otomatis. Shared header/footer dan native dropdown tetap mengikuti implementasi repository/platform; tidak dilakukan redesign.

## Laporan QA — 26 Oktober 2026 (historis)

```sh
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test apps.reviews
uv run python manage.py test
uv run ruff check apps/reviews config/settings.py config/urls.py
uv run ruff format --check apps/reviews config/settings.py config/urls.py
uv run ruff check .
uv run python manage.py tailwind build
node --check apps/reviews/static/reviews/reviews.js
git diff --check
```

- Django check: lulus. Migration dry-run: tidak ada perubahan; tidak ada migration baru/yang diterapkan ke database aplikasi dalam finalisasi ini.
- Reviews: **29 tests lulus** (16 tests lama diadaptasi menggunakan MenuItem UUID asli, 13 tests tambahan).
- Seluruh proyek: **121 tests, 120 lulus, 1 gagal**, pada `apps.designsystem.tests.DesignSystemPageTests.test_page_is_public_and_uses_application_shell`: mengharapkan `href="/#manfaat"` yang sudah diganti header dengan `/catalog/`. Kegagalan yang sama direproduksi dari arsip **HEAD sebelum perubahan**, di direktori sementara. Test/header tersebut tidak diubah untuk menjaga scope.
- Ruff file Reviews dan config yang diperiksa: lulus. Format: lulus. Ruff repository: **6 temuan lama** di Catalog (imports/unused imports pada admin/forms/models/views), juga direproduksi dari arsip HEAD. Tidak dilakukan auto-fix Catalog.
- Tailwind build, JavaScript syntax, dan whitespace diff: lulus.
- Django mengeluarkan warning bahwa direktori `staticfiles/` belum ada. Build CSS berhasil; `collectstatic` tetap bagian prosedur deployment tim. Respons kegagalan Nominatim dalam test Map berasal dari skenario mock, bukan kegagalan test.

Cakupan tests: metadata/foto/tenant nullable, canonical UUID/404, isolasi menu dan summary, rename/delete menu, preservasi identifier lama, CRUD dan photo cleanup, guest/customer/tenant/owner permissions, login next, spoofed author/menu/packaging, rating/distribution/average, seluruh satisfaction/sentiment dan kombinasi filter, sorting/pagination, helpful toggle/unique constraint, CSRF, escaping, query tanpa N+1, tanpa Orders dan kontrak reusable/compostable/invalid adapter.

Browser QA memakai server loopback terpisah dan database/media sementara dengan MenuItem UUID asli. Database aplikasi tidak digunakan. Terverifikasi:

- Catalog tenant → Read Reviews; nama/tenant/deskripsi/foto benar.
- Guest login modal → Accounts → kembali ke Reviews.
- Publish 6 → 7 review; edit rating/teks dan toast updated; delete confirmation → 6 review dan toast deleted.
- Helpful 0 → 1 selected → 0, Load More empat → tujuh kartu sebelum penghapusan.
- Kombinasi Rating + Positive menampilkan dua chip, no matching state, URL filter yang sesuai.
- Menu kedua menampilkan empty state terpisah.

Upload/replace/remove foto dan invalid requests diverifikasi pada tests backend; dialog file OS, network failure injection/retry, serta seluruh viewport desktop/mobile belum diverifikasi lewat browser dalam audit ini.

## Perubahan dan kesiapan review — 26 Oktober 2026 (historis)

File diubah: `apps/reviews/integration.py`, `models.py`, `selectors.py`, `views.py`, `tests.py`, `static/reviews/reviews.js`, `templates/reviews/modal_base.html`, README ini; `config/settings.py`; dan dua tautan pada `apps/catalog/templates/catalog/catalog_tenant.html`. Tidak ada perubahan model/view Catalog, Accounts, Map, Orders, shared Design System, atau migrations.

Integrasi dan fitur inti Reviews siap **direview tim / calon PR**. Belum dinyatakan 100% production-ready karena suite repository belum seluruhnya hijau dan ada batas pengujian visual/operasional di atas. Integrasi Orders tetap opsional. Tidak ada commit, push, merge baru, PR, reset/flush database, perubahan identitas Git, atau perubahan `.env`.

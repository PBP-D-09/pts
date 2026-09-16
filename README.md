## Description
Gaya hidup masyarakat perkotaan yang makin padat membuat banyak orang kesulitan menjaga konsistensi pola makan sehat. Layanan pengantaran makanan sering kali menjadi pilihan utama pengguna, tetapi membawa dampak buruk, yaitu penumpukan sampah plastik sekali pakai dan tingginya jejak karbon dari pengiriman individual yang tidak efisien. Di sisi lain, pembeli sering bingung memastikan dari mana asal bahan makanan yang mereka konsumsi.

SustainaBowl hadir sebagai platform healthy meal ordering platform yang mengintegrasikan sustainability pada setiap transaksi. Pengguna tidak hanya memesan makanan, tetapi juga memerhatikan paket bekal sehat yang dipersonalisasi sesuai kebutuhan diet mereka dan kesehatan lingkungan.

### Apa manfaat SustainaBowl?
* Membantu masyarakat menjaga asupan gizi harian secara terencana tanpa perlu pusing memikirkan menu setiap hari atau takut kebablasan mengonsumsi junk food.
* Menghentikan penggunaan kemasan sekali pakai dengan menyediakan opsi wadah ramah lingkungan (reusable container atau compostable box).

## Identitas Anggota
* Joachim Susatiyo (2506602694)
* Muhammad Zaky Robbani (2506597712)
* I Komang Arka Darma Laksana (2506656791)
* Awiddy Munaya Rajanadoli (2506622872)
* Anantha Kamal Eirian (2506656425)

## Pembagian Modul
### accounts
manajemen user (bisa tambahin preferensi diet), sistem akumulasi poin ramah lingkungan (Eco Points) untuk user dan memberikan plan makanan yang sesuai.

* custom User Model (Auth Login/Register).
* profile preferensi diet (Vegan, Vegetarian, Low Carb, Keto, Allergies).

API: Spoonacular API/Open Food Facts API/Edamam (untuk melihat nutrisi makanan [spoonacular](https://spoonacular.com/food-api) [openfoodfacts](https://openpublicapis.com/api/open-food-facts) [edamam](https://www.edamam.com/))

**Anggota Bertanggungjawab: Joachim Susatiyo**

#### Requirements
* Create: Pendaftaran akun baru, pembuatan profil user, dan inisialisasi preferensi diet (Vegan, Keto, dll).
* Read: Menampilkan profil pribadi, statistik akumulasi Eco Points, serta riwayat aktivitas diet harian.
* Update: Memperbarui data diri, informasi kontak, preferensi diet, dan foto profil.
* Delete: Menghapus preferensi diet tertentu atau mereset statistik poin pribadi.

Auth Filter: Data kontak pribadi dan akumulasi Eco Points hanya dapat diakses oleh user yang sudah terautentikasi.

API & Filter: Mengintegrasikan Spoonacular API / Open Food Facts API (atau Mock Nutrition API) untuk mengambil data batasan nutrisi harian dan memfilter rekomendasi kalori berdasarkan kategori diet user.

AJAX/HTMX: Mengubah toggle preferensi diet dan memperbarui foto profil secara realtime tanpa melakukan reload halaman.

### catalog
katalog makanan sehat, filter bahan baku

* model MenuItem, Category, dan Ingredient.
* fitur pencarian dan filter menu berdasarkan preferensi diet.
* eco points berdasarkan tipe kemasan.

API: Forkprint/CarbonCloud (carbon footprint untuk menghitung eco score [forkprint](https://www.forkprint.app/) [carboncloud](https://carboncloud.com/api/))

**Anggota Bertanggungjawab: Muhammad Zaky Robbani**

#### Requirements
* Create: Menambahkan katalog makanan menu sehat milik tenan (serta manajemen menu utama oleh Admin).
* Read: Menampilkan katalog makanan sehat lengkap dengan Eco score, harga, dan informasi alergen.
* Update: Memperbarui rincian katalog makanan, porsi, atau preferensi bahan baku dalam makanan.
* Delete: Menghapus pilihan makanan dari katalog tenan.

Auth Filter: Katalog umum dapat diakses secara bebas oleh guest, tetapi fitur bookmark/favorite wajib login.

API & Filter: Mengintegrasikan  untuk menghitung jejak karbon bahan baku, lalu filter berdasarkan rentang harga, eco-score, dan kategori makanan.

AJAX/HTMX: Fitur pencarian menu catalog dan pemfilteran kategori makanan.

### orders
checkout, keranjang belanja

* model Cart, CartItem, Order, dan OrderItem.
* fitur pemesanan dengan pilihan kemasan (reusable container, compostable box).
* sistem riwayat pesanan dan pemotongan stok menu.

API: OpenMeteoAPI (untuk mengecek cuaca dan menyesuaikan harga order [link](https://open-meteo.com/))

**Anggota Bertanggungjawab: Anantha Kamal Eirian**

#### Requirements
* Create: Membuat pesanan baru serta memilih opsi kemasan ramah lingkungan (reusable container, compostable box).
* Read: Menampilkan keranjang belanja aktif dan riwayat seluruh transaksi pesanan.
* Update: Mengubah jumlah item belanjaan atau menambahkan catatan pengiriman sebelum diproses.
* Delete: Menghapus item dari keranjang belanja atau membatalkan pesanan.

Auth Filter: Pengunjung guest hanya dapat menyimpan keranjang sementara, sedangkan pembuatan pesanan dan riwayat transaksi wajib login.

API & Filter: Mengintegrasikan OpenMeteo Weather API untuk kalkulasi penyesuaian biaya pengiriman berbasis cuaca realtime, serta menyediakan filter riwayat pesanan berdasarkan rentang tanggal dan status transaksi.

AJAX/HTMX: Menyesuaikan kuantitas item keranjang atau menghapus item langsung dari keranjang belanja via tanpa melakukan refresh halaman.

### map
integrasi peta open street map, dan tenan alamat pada map

* integrasi Leaflet.js di frontend untuk menampilkan peta.
* menampilkan lokasi tenan.

API: OpenStreetMap (untuk menampilkan peta open source [link](https://www.openstreetmap.org))

**Anggota Bertanggungjawab: Awiddy Munaya Rajanadoli**

#### Requirements
* Create: Menambahkan titik lokasi alamat pengiriman baru menggunakan pin interaktif pada peta.
* Read: Menampilkan daftar alamat pengguna yang tersimpan, dan lokasi tenan.
* Update: Mengubah rincian alamat pengiriman, patokan lokasi, atau catatan kurir.
* Delete: Menghapus titik alamat pengiriman dari daftar tersimpan.

Auth Filter: Peta publik lokasi tenan dapat dilihat oleh umum, sedangkan pengurusan daftar alamat pribadi terbatas pada pemilik akun tenan.

API & Filter: Mengintegrasikan OpenStreetMap Nominatim API untuk pencarian alamat dan lokasi.

AJAX/HTMX: Pencarian alamat menggunakan HTMX/AJAX yang secara langsung memperbarui pin pada peta.

### review
feedback kualitas makanan dan kemasan.

* model Review dan Rating per menu makanan.
* rating untuk Rasa dan Kesesuaian Kemasan Ramah Lingkungan.
* user bisa upload foto makanan dan memberikan saran perbaikan kemasan.

API: SentimentAnalysisAPI (untuk mengetahui sentimen review [link](https://sentiment-analysis-api.solvcraft.workers.dev))

**Anggota Bertanggungjawab: I Komang Arka Darma Laksana**

#### Requirements
* Create: Upload review baru, memberikan rating rasa & kemasan ramah lingkungan, serta dapat melampirkan foto makanan.
* Read: Menampilkan daftar review pelanggan pada halaman tenan atau detail khusus makanan beserta skor kepuasan kemasan.
* Update: Mengedit teks review, penyesuaian rating, atau memperbarui foto review pribadi.
* Delete: Menghapus review yang telah dipublikasikan oleh user.

Auth Filter: Seluruh review dapat dibaca secara umum oleh guest, tetapi action membuat, mengedit, dan menghapus review hanya diperbolehkan bagi user yang membuatnya.

API & Filter: Mengintegrasikan Sentiment Analysis API untuk mendeteksi sentimen review (positive/neutral/negative), serta menyediakan filter review berdasarkan tingkat rating, sentimen teks, dan kepuasan kemasan.

AJAX/HTMX: Pengiriman review baru, upvote review bermanfaat, serta penyaringan review secara dinamis tanpa refresh halaman.

## User Personas
### Customer
Masyarakat yang ingin menjaga pola makan sehat sekaligus meminimalkan dampak sampah lingkungan dari pesanan makanan harian.

* accounts: Mendaftar akun, mengelola profil pribadi, memilih preferensi diet (Vegan, Keto, Alergi), serta melihat akumulasi Eco-Points.
* catalog: Mengakses katalog makanan sehat, memfilter menu berdasarkan Eco score, rentang harga, atau membuat resep kustom sehat.
* orders: Menambahkan makanan ke keranjang, memilih jenis kemasan (Reusable Box vs Compostable Box), melakukan checkout, dan melihat riwayat pesanan.
* map: Menentukan dan menyimpan titik alamat pengiriman interaktif menggunakan peta OpenStreetMap (OSM).
* review: Memberikan review rating rasa makanan, mengunggah feedback makanan.

### Admin
Tim operasional setiap tenan yang bertugas mengelola katalog menu, memproses pesanan masuk, serta memantau operasional tenan dan lokasi pengiriman.

* accounts: Memantau data pengguna terdaftar dan melihat ringkasan statistik preferensi diet pelanggan untuk perancangan menu.
* catalog: Melakukan manajemen penuh (CRUD) katalog menu utama, mengedit Eco score, dan mengatur ketersediaan bahan baku lokal.
* orders: Mengelola dan memperbarui status pesanan pelanggan, serta memantau sisa stok kemasan reusable.
* map: Mengatur dan memperbarui titik lokasi tenan dan memantau cakupan radius pengiriman.
* review: Memantau seluruh review masuk, dan feedback pelanggan terkait kualitas kemasan ramah lingkungan.

## Links
* [Deployment PWS (Not Ready)](https://google.com)
* [Figma (Not Ready)](https://figma.com)

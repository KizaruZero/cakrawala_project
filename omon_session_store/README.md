# Omon Session Store (Odoo 18)

**Redis Session Store** — memindahkan penyimpanan HTTP session Odoo dari
   disk ke Redis, berguna untuk deployment multi-worker/multi-container.


## Instalasi Dasar
1. Copy folder `omon_session_store` ke `addons_path` server Odoo Anda (mis. `/mnt/extra-addons/omon_session_store`).
2. Update Apps List, cari "Omon Session Store", klik Install.
   (Instalasi lewat Apps ini **cukup untuk fitur Subscription Monitor saja**.
   Untuk Redis Session Store, ada langkah tambahan wajib — lihat di bawah.)

---
1. Redis Session Store

### a. Install dependency Python
```bash
pip install redis
```

### b. WAJIB: daftarkan sebagai server-wide module
Session ditangani Odoo **sebelum** database dipilih dan sebelum modul biasa
di-load lewat Apps, jadi fitur ini **tidak akan aktif** hanya dengan
menginstall modul lewat Apps — harus didaftarkan lewat `server_wide_modules`.

Di `odoo.conf`:
```ini
[options]
server_wide_modules = web,omon_session_store

; konfigurasi Redis (opsional, ini semua defaultnya)
session_redis_host = 127.0.0.1
session_redis_port = 6379
session_redis_db = 1
session_redis_password =
session_redis_ssl = False
session_redis_prefix = omon-session:
session_redis_expiration = 604800
```

Atau lewat command line:
```bash
odoo-bin -c odoo.conf --load=web,omon_session_store
```

Semua parameter di atas juga bisa diisi lewat environment variable
(prioritas lebih tinggi dari odoo.conf): `SESSION_REDIS_HOST`,
`SESSION_REDIS_PORT`, `SESSION_REDIS_DB`, `SESSION_REDIS_PASSWORD`,
`SESSION_REDIS_SSL`, `SESSION_REDIS_PREFIX`, `SESSION_REDIS_EXPIRATION`.

### c. Restart Odoo
Cek log saat startup, harus muncul baris seperti:
```
... omon_session_store: session Odoo sekarang disimpan di Redis (host=127.0.0.1 db=1 prefix=odoo-session: expiration=604800s)
```

Kalau Redis tidak bisa dihubungi, otomatis fallback ke filesystem session
store default Odoo (server tidak akan crash), error dicatat di log — cek
koneksi Redis Anda kalau ini terjadi.

### d. Verifikasi
```bash
redis-cli -n 1 keys "odoo-session:*"
```
Harus muncul key session setelah Anda login ke Odoo.

### Catatan Redis Session Store
- Fitur ini **tidak perlu** diinstall di database manapun lewat Apps; cukup
  terdaftar di `server_wide_modules`. Menginstallnya lewat Apps juga tidak
  masalah, hanya tidak wajib untuk fitur ini secara spesifik.
- TTL/masa berlaku session di Redis mengikuti `session_redis_expiration`
  (default 7 hari), bukan `session.gc()` bawaan Odoo yang basisnya file.
- Karena hook ini jalan sebelum database dipilih, konfigurasi Redis **tidak**
  bisa diletakkan di Settings UI (butuh DB) — harus lewat `odoo.conf`/env var.

---

## 3. Menu Admin: Kelola & Hapus Session

Setelah Redis Session Store aktif (lihat bagian 2 di atas), tersedia menu
khusus **Administrator** (`base.group_system`) di navigasi utama:

**Omon Session Store > Kelola Session Aktif**
- Menampilkan snapshot semua session yang sedang tersimpan di Redis saat
  ini: login user, User ID, potongan Session ID, dan sisa waktu (TTL).
- Setiap baris punya tombol **Hapus** — menghapus session tersebut dari
  Redis, sehingga user pemilik session itu otomatis ter-logout pada
  request berikutnya (di perangkat/browser tempat session itu dipakai).
- Kalau Redis Session Store sedang tidak aktif (mis. modul belum
  didaftarkan di `server_wide_modules`, atau Redis gagal konek saat
  startup), menu ini akan menampilkan pesan error yang jelas, bukan crash.

**Omon Session Store > Hapus Semua Session**
- Wizard konfirmasi untuk menghapus **SEMUA** session sekaligus — akan
  memaksa logout semua user yang sedang login, di semua perangkat/browser.
- Berguna misalnya setelah insiden keamanan, rotasi credential, atau saat
  perlu memastikan semua orang login ulang.
- Ada dialog konfirmasi eksplisit (menampilkan jumlah session yang akan
  terhapus) sebelum tombol "Ya, Hapus Semua Session" bisa diklik — supaya
  tidak ke-klik tidak sengaja.

---

## Catatan Keamanan
- Password Redis (`session_redis_password`) sebaiknya diisi lewat environment
  variable, bukan ditulis polos di `odoo.conf` yang bisa terbaca banyak orang.
- Dapatkan layanan Tambahan untuk installasi server Odoo Terbaik. 
  Segera Hubungi kami
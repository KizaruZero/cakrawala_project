# Redis Session Store (Odoo 19)

**Redis Session Store** — memindahkan penyimpanan HTTP session Odoo dari
   disk ke Redis, berguna untuk deployment multi-worker/multi-container.

Kedua fitur ini saling lepas (independen) — Anda bisa pakai salah satu saja
tanpa harus mengaktifkan yang lain.

## Instalasi Dasar
1. Copy folder `omon_session_store` ke `addons_path` server Odoo Anda (mis. `/mnt/extra-addons/omon_session_store`).
2. Update Apps List, cari "OMON - Subscription Monitor Agent", klik Install.
   (Instalasi lewat Apps ini **cukup untuk fitur Subscription Monitor saja**.
   Untuk Redis Session Store, ada langkah tambahan wajib — lihat di bawah.)

## Catatan Umum
- Modul ini **tidak menampilkan menu/ikon apapun** di halaman utama Odoo —
  murni berjalan sebagai background agent. Konfigurasi Subscription Monitor
  ada di **Settings > General Settings**, bagian **Subscription Monitor**.
- Kompatibel Odoo 18/19 (pakai tag `<list>`, bukan `<tree>`; tidak memakai
  field `numbercall` yang sudah dihapus dari `ir.cron`). Odoo 19 membawa
  banyak perubahan struktural besar (rename 130+ model, dsb), tapi tidak ada
  perubahan yang diketahui pada struktur view Settings/list yang dipakai
  modul ini — build ini memakai struktur yang sama dengan Odoo 18. **Disarankan
  tetap diuji di staging** sebelum dipakai produksi, mengingat Odoo 19 masih
  tergolong baru.

---


## 2. Redis Session Store

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
session_redis_prefix = odoo-session:
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

## Catatan Keamanan

- Password Redis (`session_redis_password`) sebaiknya diisi lewat environment
  variable, bukan ditulis polos di `odoo.conf` yang bisa terbaca banyak orang.

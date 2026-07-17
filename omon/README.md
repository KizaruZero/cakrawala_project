# OMON - Subscription Monitor Agent (Odoo 18)

Modul agent yang mengumpulkan info instance Odoo lalu mengirimkannya ke
dashboard eksternal (mis. `api.odoo.my.id`) via HTTPS POST + Bearer API Key.

## Instalasi
1. Copy folder `omon` ke `addons_path` server Odoo Anda (mis. `/mnt/extra-addons/omon`).
2. Update Apps List, cari "OMON - Subscription Monitor Agent", klik Install.

## Catatan
- Modul ini **tidak menampilkan menu/ikon apapun** di halaman utama Odoo —
  murni berjalan sebagai background agent. Semua konfigurasi ada di dalam
  **Settings > General Settings**, bagian **Subscription Monitor**.
- Kompatibel Odoo 18 (pakai tag `<list>`, bukan `<tree>`; tidak memakai field
  `numbercall` yang sudah dihapus dari `ir.cron`).

## Konfigurasi
Buka **Settings > General Settings**, scroll ke bagian **Subscription Monitor**:
- **URL Dashboard (API Endpoint)** — misal `https://api.odoo.my.id/api/v1/instances/report`
- **API Key** — token yang didaftarkan dari dashboard untuk instance ini
- **Tanggal Kadaluarsa Manual** — isi jika ini instance Community (Enterprise
  otomatis membaca `database.expiration_date`)
- Centang **Aktifkan Pengiriman Berkala**, lalu klik **Sync Sekarang / Test Koneksi**
  untuk memastikan koneksi ke dashboard berhasil sebelum mengandalkan cron.

## Data yang dikirim (JSON)
```json
{
  "instance_uuid": "uuid-persisten-per-database",
  "database_name": "nama_db",
  "domain": "https://client.example.com",
  "odoo_version": "16.0",
  "edition": "enterprise/community",
  "active_internal_users": 12,
  "active_total_users": 15,
  "companies": [{"name": "...", "vat": "...", "country": "..."}],
  "main_company": "PT Contoh",
  "subscription_expiration_date": "2026-12-31",
  "installed_apps_count": 34
}
```

## Cron
Scheduled Action "Subscription Monitor: Sync ke Dashboard" berjalan tiap 1 hari
(bisa diubah lewat Settings > Technical > Scheduled Actions).

## Riwayat Pengiriman
Menu **Subscription Monitor > Riwayat Sync** (khusus group Administrator/Settings)
menampilkan log tiap percobaan kirim: status, payload, dan response server —
berguna untuk debugging integrasi dengan dashboard.

## Catatan Keamanan
- API Key disimpan sebagai `ir.config_parameter` biasa (field password di UI).
  Untuk keamanan lebih, simpan di environment variable server dan proteksi
  akses menu ini hanya untuk group Administrator (`base.group_system`).
- Endpoint dashboard **wajib** menggunakan HTTPS dan memvalidasi API Key per
  instance sebelum menyimpan data yang masuk.

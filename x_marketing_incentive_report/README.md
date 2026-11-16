# Report Insentif Marketing (19.0.1.0.0)

Laporan insentif marketing per unit untuk CRS.

## Cara kerja
- Menu: **Rental → Reporting → Insentif Marketing**.
- **Ambil Data Insentif**: pilih periode (Tgl Live). Modul membaca Rental Order Line
  yang berasal dari RPC, produknya kendaraan, dan Actual Delivery-nya jatuh di periode itu.
- Angka diambil dari RPC sesuai **Harga Sewa Final** (Batas Atas/Bawah):
  Insentif per unit = Jumlah Insentif RPC ÷ Jumlah Unit RPC.
- Unit dicari dari lot pada pengiriman keluar (done) → Fleet. Cadangan: analytic account baris.
- **EV** (Fuel Type Fleet = Electric) dikali rasio `x_marketing_incentive_report.ev_ratio`
  (default 0.8). Selain Electric (termasuk hybrid) dihitung ICE 100%.
- RPC dengan Summary insentif = NO → insentif 0 dengan catatan syarat yang gagal.
- Baris yang sudah diambil **tidak berubah** saat Ambil Data diulang (angka terkunci).
  Manager bisa **Hitung Ulang** per baris atau per periode.

## Yang tidak disentuh
Modul ini hanya membaca RPC, Rental Order, stok dan Fleet. Tidak ada field atau logika
yang ditambahkan ke modul lain; semua data laporan ada di tabel `x_marketing_incentive_line`.

## Hak akses
- **Insentif Marketing: User**: lihat laporan dan ambil data periode baru.
- **Insentif Marketing: Manager**: + hitung ulang dan hapus. Admin otomatis masuk grup ini.

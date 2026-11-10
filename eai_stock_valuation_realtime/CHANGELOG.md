# Changelog — eai_stock_valuation_realtime (Odoo 19)

Format versi: `19.0.MAJOR.MINOR.PATCH`. Setiap rilis dikirim sebagai zip terpisah; rilis lama tidak ditimpa.

## 19.0.1.0.2 — 4 Nov 2026

Perbaikan dari review tim (4 Nov 2026):

- **Laporan Saldo Interim Valuasi per company:** record rule baru, user hanya melihat saldo
  perusahaan yang dipilih (allowed companies).
- **Credit note vendor multi-baris:** qty penutup klaim dihitung dari total semua baris pada
  credit note yang sama untuk PO line yang sama. Contoh: retur 1 unit, credit note 2 baris x 0,6
  sekarang ditolak (sebelumnya lolos dan Piutang Klaim minus).
- **Qty laporan interim:** jurnal koreksi nilai (bill telat beda harga, landed cost, dll.) dan
  baris selisih klaim credit note tidak lagi membawa qty, sehingga qty tidak terhitung dua kali.
  Migrasi saat Upgrade menolkan qty pada baris lama yang sudah terposting (nilai tidak berubah).
- 5 tes baru (`test_eai_rt_review_fixes.py`); total 33 tes.

## 19.0.1.0.1 — 2 Nov 2026

- Perbaikan: credit note vendor dalam valuta asing (mis. USD/EUR) dengan nilai berbeda dari
  klaim retur. Baris selisih klaim sebelumnya tercatat dengan nilai valuta asing di kolom mata
  uang perusahaan (contoh: Rp27,78 seharusnya Rp500.000), sehingga Piutang Klaim tidak kembali nol.
  Sekarang baris dicatat dalam mata uang perusahaan; selisih (termasuk selisih kurs terhadap
  klaim) ke akun selisih harga retur.
- Tes baru `test_eai_rt_fx.py` (7 skenario valuta asing): GR lalu bill kurs lain, bill dulu,
  retur + credit note kurs lain, SO/invoice valuta asing, retur jual + credit note customer,
  bill telat setelah terjual, credit note reset ke draft.

## 19.0.1.0.0 — 29 Okt 2026

Port dari versi Odoo 20 (20.0.1.0.1). Logika jurnal sama; penyesuaian untuk Odoo 19:

- HPP invoice: hook `_stock_account_prepare_realtime_out_lines_vals` (baris `cogs` Odoo 19),
  sisi kredit dialihkan ke Stock Output untuk kategori bertanda.
- Selisih klaim credit note vendor dibuat sebagai baris `cogs` saat posting (ikut terhapus saat
  reset ke draft).
- Nilai barang keluar Odoo 19 disimpan positif: mesin memakai nilai bertanda internal.
- Koreksi nilai receipt (bill telat beda harga) dipecah: porsi barang di stok ke Persediaan,
  porsi barang yang sudah keluar ke akun selisih harga retur (GL = nilai valuasi Odoo 19).
- Landed cost: hanya porsi qty yang masih di stok yang dikapitalisasi (standar Odoo 19).
- Stock Closing: pengecualian lewat `_get_accounts_by_product` dan `stock_accounting_value`
  (Odoo 19 tidak punya accrual).
- Scrap dikenali dari `scrap_id` pada stock move.
- Modul landed cost digabung ke modul utama (satu folder); dependensi `stock_landed_costs`.
- Label: "Price Difference Account" kategori diganti "Return Price Difference Account"
  (menghindari bentrok dengan field standar).
- Hak akses format `ir.model.access.csv`.
- 21 tes otomatis.

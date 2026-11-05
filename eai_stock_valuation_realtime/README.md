# EAI — Real-time Stock Valuation untuk Odoo 19

Modul ini mengembalikan jurnal persediaan **per pergerakan stok** (seperti Odoo 17) khusus
untuk kategori produk yang ditandai. Kategori lain tetap 100% perilaku standar Odoo 19.

Versi ini adalah port dari `eai_stock_valuation_realtime` 20.0.1.0.1 (Odoo 20). Logika jurnal
sama; perbedaannya ada di "Catatan khusus Odoo 19" di bawah.

## Isi paket

Satu folder, satu modul: `eai_stock_valuation_realtime` (termasuk dukungan landed cost).

Dependensi: `stock_account`, `purchase_stock`, `sale_stock`, `stock_landed_costs`.

## Instalasi

1. Salin folder ke addons path, restart Odoo, Update Apps List.
2. Install **EAI - Real-time Stock Valuation**.
3. Uji di sandbox dulu (lihat "Pengujian").

## Konfigurasi

1. Buat akun di COA (contoh nama):
   - Persediaan dalam Perjalanan (Stock Input)
   - Barang Terkirim Belum Ditagih (Stock Output)
   - Piutang Klaim Retur Pembelian
   - Selisih Nilai Retur Persediaan
   - Selisih Persediaan, Beban Persediaan Rusak (bila belum ada)
2. **Inventory > Configuration > Product Categories > (kategori LM Emas / LM Silver)**
   - Inventory Valuation = Perpetual (at invoicing), Costing Method = Average Cost (AVCO)
   - Di bawah **Account Properties**, centang **Real-time Valuation**
   - Isi Stock Input Account, Stock Output Account (wajib), Return Price Difference Account,
     Return Claim Account, Inventory Adjustment Account, Scrap Account.
3. Opsional: **Inventory > Settings > Valuation > Real-time Stock Valuation** untuk akun default
   (klaim, selisih, rusak) dan pilihan jurnal Posted/Draft.
4. Opsional: **Gudang > Analitik Valuasi (butik)** agar jurnal membawa analitik butik.
5. Produk LM: **Control Policy = On ordered quantities** (tab Purchase), supaya qty bill yang
   dibuat sebelum barang diterima sama dengan PO.

> **Cut-over:** aktifkan flag sebelum transaksi pertama. Bila diaktifkan saat sudah ada stok,
> transaksi lama dianggap sudah tercermin di GL (tidak dijurnal ulang); hanya perubahan setelah
> aktivasi yang dijurnal. Jalankan Stock Closing standar sekali **sebelum** mengaktifkan flag
> supaya saldo awal bersih.

## Jurnal yang dibentuk

| Titik | Jurnal |
|---|---|
| Vendor bill | Dr Stock Input / Cr AP |
| Receipt (Diterima) | Dr Persediaan / Cr Stock Input |
| Retur ke vendor | Dr Piutang Klaim (qty x harga bill asal), Dr/Cr Selisih Harga Retur, Cr Persediaan (rata-rata) |
| Credit note vendor (qty diretur) | Dr AP / Cr Piutang Klaim; selisih nilai ke akun selisih harga retur |
| Credit note vendor (qty belum diterima) | Dr AP / Cr Stock Input |
| Delivery (DO) | Dr Stock Output / Cr Persediaan (rata-rata) |
| Invoice final | Pendapatan standar + Dr HPP / Cr Stock Output (nilai DO) |
| Invoice DP | Standar, tanpa HPP |
| Retur jual | Dr Persediaan / Cr Stock Output (nilai DO asal) |
| Credit note customer | Pendapatan dibalik + Dr Stock Output / Cr HPP |
| Opname | Persediaan vs Selisih Persediaan |
| Scrap | Dr Persediaan Rusak / Cr Persediaan |
| Transfer antar butik | Tidak ada jurnal |
| Landed cost | Dr Persediaan / Cr akun biaya landed cost, **hanya porsi qty yang masih di stok** |
| Koreksi nilai (bill telat beda harga, koreksi qty) | Delta nilai, tanggal hari koreksi; porsi barang yang sudah keluar ke selisih harga |

Semua jurnal ada di jurnal Inventory Valuation, partner dari dokumen asal, referensi dokumen stok,
dan bisa dibuka dari tombol **Jurnal Valuasi** di transfer.

## Laporan

Hanya menampilkan saldo perusahaan yang dipilih user (multi-company).

**Accounting > Reporting > Management > Saldo Interim Valuasi** (juga di Inventory > Reporting):
saldo terbuka per dokumen asal, butik, dan produk untuk Stock Input (dalam perjalanan),
Stock Output (terkirim belum ditagih), dan Piutang Klaim Retur, beserta umur hari.

## Catatan khusus Odoo 19 (beda dengan versi Odoo 20)

1. **Rata-rata keluar tidak dihitung ulang mundur.** Odoo 19 menilai barang keluar dengan
   rata-rata saat move divalidasi; nilai DO lama tidak berubah bila bill datang belakangan
   dengan harga lain. Addon memecah koreksi nilai receipt: porsi barang yang masih di stok ke
   Persediaan, porsi barang yang sudah keluar ke akun selisih harga retur. GL persediaan tetap
   sama dengan nilai valuasi Odoo 19 (di Odoo 20 porsi itu masuk lewat koreksi nilai DO).
2. **Landed cost** mengikuti standar Odoo 19: hanya porsi qty yang masih di stok yang masuk
   persediaan. Porsi barang yang sudah terjual tetap sebagai beban di akun biaya landed cost
   (di Odoo 20 porsi itu masuk ke nilai DO / Stock Output).
3. **Stock Closing** Odoo 19 tidak punya accrual (Billed Not Received, dst.). Addon hanya
   mengecualikan kategori bertanda dari Stock Variation global dan variasi periode.
4. **Baris HPP** invoice dibentuk lewat mekanisme baris `cogs` Odoo 19; sisi kredit dialihkan
   ke Stock Output. Baris selisih klaim di credit note vendor juga dibuat sebagai baris `cogs`,
   sehingga ikut terhapus bila credit note di-reset ke draft dan dibuat ulang saat diposting.
5. Hak akses memakai format `ir.model.access.csv` (Odoo 19).

## Transaksi valuta asing

PO, SO, bill, invoice, dan credit note boleh dalam valuta asing. Semua jurnal valuasi addon
dalam mata uang perusahaan (IDR); konversi mengikuti Odoo:

- Receipt dinilai dengan harga PO pada kurs saat diterima; begitu bill diposting, nilai barang
  mengikuti nilai bill (kurs tanggal bill). Selisih kurs GR vs bill masuk ke Persediaan lewat
  jurnal koreksi (bukan ke akun selisih kurs).
- Klaim retur = nilai bill asal (IDR). Credit note vendor dengan kurs lain: selisihnya ke akun
  selisih harga retur.
- Invoice customer valuta asing: HPP = nilai DO (IDR); pendapatan dikonversi standar.
- Selisih kurs pelunasan (payment) tetap ditangani standar Odoo.

## Batasan yang diketahui

1. **Exchange (ANTAM mengganti barang):** receipt pengganti dijurnal Cr Stock Input, bukan
   Cr Piutang Klaim. Klaim tetap terbuka di laporan sampai Finance memutuskan perlakuannya.
2. **Credit note vendor** yang mencampur qty diretur dan qty yang belum pernah diterima dalam
   satu baris ditolak dengan pesan; pisahkan menjadi dua baris.
3. **Rata-rata per perusahaan** (standar Odoo), bukan per butik.
4. Baris jurnal manual di akun persediaan yang memakai produk kategori bertanda juga dikecualikan
   dari Stock Closing.
5. Diuji di Odoo 19.0 **Community**. Interaksi dengan laporan Enterprise wajib diuji di sandbox
   Enterprise.
6. Status pickup (Menunggu Bayar / Belum / Sudah / POD) bukan bagian modul ini (E-09).

## Pengujian

Tes otomatis ada di `tests/` (33 skenario, termasuk angka LM 10 Gram dari tes manual 20 Okt 2026,
landed cost, scrap, reset credit note, bill telat setelah barang terkirim, transaksi valuta asing, dan temuan review tim 4 Nov 2026):

```
odoo-bin -d <db> -u eai_stock_valuation_realtime --test-enable \
  --test-tags /eai_stock_valuation_realtime --stop-after-init
```

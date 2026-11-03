# Data Cleanup (Pre-Production) — Odoo 19

Membersihkan data transaksi dari database staging/test sebelum dijadikan database production.
Master data dan konfigurasi tidak pernah dihapus.

## Cara pakai

1. Install addon `x_data_cleanup` di **salinan** database. Preset klasifikasi (standar Odoo + addons
   Cakrawala) dan aturan relasi otomatis dimuat.
2. Buka **Settings > Data Cleanup > Dashboard**, lalu klik **Buka Kunci (4 jam)**. Kunci hanya berlaku
   untuk database ini (nama + UUID), jadi salinan yang di-restore tetap terkunci.
3. Pilih salah satu cara:
   - **Per dokumen:** buka list view dokumen (SO, PO, Invoice, Transfer, SPK, BASTK, RPC, ...), pilih
     record, lalu **Action > Data Cleanup: Hapus beserta turunan**.
   - **Per model:** Klasifikasi Model > tombol **Hapus Semua** di baris model.
   - **Semua transaksi:** Dashboard > **Hapus Semua Transaksi**.
4. Klik **Hitung Preview**. Yang ditampilkan:
   - jumlah record per tabel yang dihapus dan alasannya (dipilih, baris, turunan, induk, rekonsiliasi, cascade),
   - referensi yang hanya dikosongkan (record-nya tetap ada),
   - peringatan dokumen lain yang ikut terhapus di luar pilihan,
   - hasil **simulasi**: rencana dijalankan sungguhan lalu di-rollback, jadi kalau database akan
     menolak, ketahuan di sini.
   Tombol kaca pembesar di tiap baris menampilkan record yang akan dihapus.
5. Centang backup, ketik nama database, lalu **Hapus Sekarang**. Semua tercatat di **Log**.
6. **Reset Sequence** (Dashboard) untuk menomori ulang dokumen. Saat "Hapus Semua Transaksi" ini
   otomatis dijalankan.
7. **Uninstall addon ini sebelum database dipakai sebagai production.**

## Cara kerja

- Relasi dibaca dari foreign key PostgreSQL, jadi addon custom ikut tercakup tanpa didaftarkan satu per satu.
- Model diklasifikasi menjadi **Transaksi** (boleh dihapus), **Master/Konfigurasi**, atau **Perlu Review**
  (keduanya dilindungi). Model yang belum diklasifikasi juga dilindungi.
- Record yang merujuk data yang dihapus:
  - baris transaksi wajib (FK cascade / NOT NULL) → ikut dihapus,
  - referensi opsional → dikosongkan,
  - master yang akan ikut terhapus atau wajib merujuk → **ditolak**, tidak ada yang dihapus.
- **Aturan Relasi** melengkapi yang tidak tersirat dari foreign key, misalnya delivery dan invoice adalah
  turunan SO, PO turunan PR/RPC/SPK, picking dan move satu dokumen. Bisa diubah di menu Aturan Relasi.
- Pembayaran yang terekonsiliasi dengan invoice yang dihapus ikut dihapus (satu tingkat). Rekonsiliasi
  dengan dokumen lain dilepas, dan dokumen itu kembali belum lunas.
- Hapus memakai SQL, melewati blokir `unlink()` addon custom. Tabel yang ditolak FK dicoba ulang, dan siklus
  referensi diputus otomatis. **Semua-atau-tidak**: kalau ada yang gagal, tidak ada yang terhapus.
- Setelah hapus: chatter, follower, aktivitas, lampiran, dan XML id milik record yang dihapus ikut dibersihkan
  (chatter record master tidak disentuh). Stok on hand dan reservasi disesuaikan. Total, qty
  delivered/invoiced, dan status dokumen terkait yang dipertahankan dihitung ulang. Lock date dikosongkan
  (mode semua). Status unit fleet bisa direset (opsional, unit tidak pernah dihapus).

## Keputusan klasifikasi Cakrawala (preset)

- Dihapus: CRM lead, Helpdesk ticket, RPC + semua line, SO/rental + billing engine, PR + approval, PO + input
  line + approval, picking/move/quant/batch/scrap, BASTK, SPK + line/approval + histori ban/aki, BAK,
  Replacement Car, Service Planning, Disposal Bidding, jurnal/invoice/payment/rekonsiliasi, Payment Order,
  Voucher, Deferred entry, Asset (kecuali model asset), Leasing (account.loan), Leasing Simulation.
- Dipertahankan: unit fleet, lot/serial, fleet document/kontrak (STNK, asuransi), histori plat, data ban/aki
  terpasang, semua master RPC/CRM/SPK/BASTK/approval, produk, partner, COA, jurnal, pajak, gudang, user.

## Catatan

- Diuji di Odoo 19 Community (sale, purchase, stock, account, fleet, crm). Modul Enterprise dan addons
  Cakrawala belum bisa diuji langsung, jadi **jalankan preview + simulasi di salinan database dulu**.
- Jalankan **Pindai Model Belum Diklasifikasi** setelah install untuk melihat model berisi data yang belum
  punya klasifikasi.
- Nilai persediaan (valuation) dari quant yang dipertahankan tidak dihitung ulang. Cek setelah hapus parsial.
- File lampiran di filestore ditandai untuk garbage collection Odoo, bukan dihapus langsung.

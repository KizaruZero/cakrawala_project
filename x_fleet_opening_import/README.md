# Fleet Opening Import (Odoo 19)

Import unit kendaraan awal dalam satu kali proses: Fleet Number (SN), Analytic, Fleet, dan stok.

## Menu
- Inventory > Operations > Adjustments > **Import Unit Awal**
- Fleet > Configuration > **Import Unit Awal**

Butuh hak **Inventory Administrator** dan **Fleet Administrator**.

## Alur
1. **Download Template**. Sheet `Unit` (satu baris per unit), `Referensi` (pilihan valid dari database, sekaligus dropdown) dan `Petunjuk`.
2. Upload, lalu **Cek File**. Semua baris disimulasikan lalu di-rollback. Hasilnya per baris: Baru / Sebagian sudah ada / Sudah ada semua / Error, dengan alasannya.
3. **Import** hanya muncul kalau tidak ada error. Import bersifat semua-atau-tidak-sama-sekali: kalau saat import ternyata ada baris gagal, tidak ada data yang tersimpan dan errornya ditampilkan.

Per baris dibuat, atau dipakai ulang bila sudah ada:

| Langkah | Hasil |
|---|---|
| Fleet Number | `stock.lot` dengan produk, rangka, mesin, plat awal, model, tahun, warna |
| Analytic | nama = Fleet Number, Asset Number = Fleet Number, plan pertama (atau kolom Analytic Plan). Saat STNK di-Running, namanya otomatis jadi "Plat - Fleet Number" (record yang sama, tidak dobel) |
| Fleet | terhubung ke Fleet Number dan Analytic; plat, status, sub status |
| Stok | qty 1 di Lokasi Stok lewat inventory adjustment yang langsung di-apply |

Setelah import, sequence Fleet Number (`asset.serial.number`) dinaikkan melewati nomor terbesar yang diimport.

## Kolom
Wajib: Fleet Number, Produk (Internal Reference atau nama), Model (`Merek/Model` kalau nama kembar), Lokasi Stok (nama lengkap, tipe Internal).
Opsional: Plat Awal, No. Rangka, No. Mesin, Warna, Tahun, Status, Sub Status, Analytic Plan.
Warna, Tahun, Status, Sub Status, dan Plan harus sudah ada di master. Tidak ada master yang dibuat otomatis.

## Pengaman
- Fleet Number dobel di file, produk bukan kendaraan, lokasi bukan Internal, format plat salah, master tidak ditemukan: error.
- Fleet yang sudah menunggu Fleet Number (dibuat duluan dengan Asset Number) langsung dihubungkan, tidak dibuat baru. Field yang kosong di Fleet dilengkapi; yang sudah terisi tidak ditimpa.
- Analytic dengan Asset Number yang sama dipakai ulang. Kalau analytic itu sudah dipakai Fleet lain, atau ada lebih dari satu: error.
- SN yang sudah punya stok di lokasi lain: error (pindahkan lewat transfer). Kalau stoknya sudah di lokasi yang sama: di-skip.
- Fleet berstatus nonaktif (mis. Sold) tidak disentuh. Status nonaktif juga tidak boleh dipakai di file.
- Peringatan kalau kategori produk memakai valuasi Perpetual (adjustment akan membentuk jurnal persediaan).
- File yang sama aman di-upload ulang.

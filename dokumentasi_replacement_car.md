Berikut adalah rancangan **Product Requirements Document (PRD)** untuk fitur _Replacement Car_ (Mobil Pengganti) yang terintegrasi langsung dengan proses pengeluaran stok fisik kendaraan (_Goods Issue_), berdasarkan cetak biru sistem dan percakapan kita sebelumnya:

---

# **Product Requirements Document (PRD): Fitur Replacement Car & Trigger Goods Issue**

## **1. Latar Belakang & Konsep Dasar Kendaraan sebagai "Produk"**

Untuk memahami alur perpindahan fisik mobil pada modul ini, perlu dipahami terlebih dahulu siklus hidup (lifecycle) kendaraan di dalam sistem.

**Semua mobil pada awalnya dikelola sebagai "Produk" (dengan tipe _Goods_ / _Storable Product_):**

1. **Fase Pengadaan:** Mobil bermula dari pembuatan _Purchase Request_ (PR) oleh pihak _Requestor_.
2. **Fase Pemesanan:** PR tersebut kemudian diproses menjadi _Purchase Order_ (PO) oleh tim _Purchasing_ untuk dipesan ke dealer/vendor.
3. **Fase Penerimaan:** Saat mobil fisik tiba, sistem mencatatnya melalui form _Goods Receive_ di modul _Inventory_. Di titik inilah nomor pelat awal, nomor rangka, dan nomor mesin dimasukkan. Sistem kemudian menghasilkan _Serial Number_ (Nomor Seri) yang unik.
4. **Fase Registrasi Aset:** Melalui tombol "Register Asset Detail" di form _Goods Receive_, barulah identitas "Produk" tersebut resmi didaftarkan menjadi **Aset Fleet** (Armada operasional) dengan Nomor Aset (_Asset Number_) yang secara otomatis mengambil data dari _Serial Number_ produk tersebut.

## **2. Tujuan Fitur (Objective)**

Fitur _Replacement Car_ dirancang untuk menangani permohonan dan persetujuan pemberian mobil pengganti kepada pelanggan saat mobil utama mengalami kerusakan parah (_breakdown_).

Secara khusus, ketika permohonan mobil pengganti disetujui, sistem harus otomatis memicu (_auto-trigger_) dokumen pengeluaran barang **(_Goods Issue/Delivery Order_)**. Barang/produk yang dikeluarkan di dalam _Goods Issue_ tersebut adalah **Produk Mobil Pengganti itu sendiri**, yang dirujuk melalui Nomor Seri (Asset Number) unit pengganti tersebut.

## **3. Alur Proses (Process Flow)**

Berikut adalah alur bagaimana _Replacement Car_ diajukan hingga memicu _Goods Issue_:

1. **Pembuatan SPK dari Tiket:** Pelanggan melaporkan kendala, dan tim _Asset_ membuat Surat Perintah Kerja (SPK). Jika unit mogok/rusak total, pengguna akan mencentang opsi **"Unit Breakdown?"**.
2. **Pemicu Form RC:** Centang pada "Unit Breakdown?" akan memunculkan tombol tambahan **"Create RC"** (Create Replacement Car) di form SPK. Menekan tombol ini akan menghasilkan Form Permintaan _Replacement Car_.
3. **Pengisian Form & Pengecekan Stok:** Di dalam Form RC, pengguna menentukan spesifikasi unit mobil yang akan diganti dan spesifikasi **mobil pengganti (Replacement Vehicle)**. Tim aset wajib memastikan stok mobil pengganti tersedia di sistem.
4. **Persetujuan (Matrix Approval):** Form RC diajukan untuk disetujui secara berjenjang oleh pihak berwenang (_Approver_). (Catatan: Sistem tidak mengirimkan notifikasi email secara otomatis untuk persetujuan ini).
5. **Auto-Trigger Goods Issue:** Setelah Form RC disetujui sepenuhnya (_Fully Approved_) dan stok tersedia, sistem akan men-trigger dokumen pengeluaran **Goods Issue Unit** di modul _Inventory_.
6. **Eksekusi Pengeluaran Fisik:**
   - Tim _Inventory/Asset_ membuka form _Goods Issue_ tersebut.
   - Pada baris produk (line item), **produk yang tertera adalah "Model Mobil Yang Diganti"**.
   - Pengguna wajib menginput **Serial Number (Asset Number)** dari mobil pengganti tersebut agar stoknya bisa direlease/dikeluarkan kepada pelanggan.
7. **Pembaruan Status Aset:** Setelah _Goods Issue_ selesai divalidasi, sistem akan otomatis mengubah _Fleet Sub-Status_ dari mobil pengganti tersebut menjadi **"Replacement Car"**.

## **4. Spesifikasi Kebutuhan Fungsional (Functional Requirements)**

### **A. Kondisi Pemicu (Trigger Conditions)**

- Form RC hanya bisa dibuat jika _checkbox_ `Unit Breakdown?` pada SPK bernilai _True_.
- Tombol _Action_ untuk memvalidasi/mengirim _Replacement Car_ hanya aktif setelah status di tab `Matrix Approval` berubah menjadi **Approved** untuk semua _approver_.

### **B. Pemetaan Data (Data Mapping) pada Form RC**

Formulir RC (RC/{Bulan}/{Tahun}/{Nomor Urut}) wajib menampung dua blok informasi utama:

- **Data Mobil Saat Ini (Current Vehicle):** Mencatat kendaraan klien yang bermasalah (License Plate, Vehicle, Year, Color). Mengambil data dari mobil yang ada di SPK.
- **Data Mobil Pengganti (Replacement Vehicle):** Mencatat kendaraan yang akan diberikan kepada klien. Kolom ini _mandatory_ (wajib diisi):
  - `Company Client (Replacement)`
  - `License Plate (Replacement)`
  - `Vehicle (Replacement)` -> **Ini adalah referensi produk/mobil yang akan ditarik ke dalam Goods Issue**.
  - `Year (Replacement)`
  - `Color (Replacement)`

### **C. Integrasi Goods Issue (Inventory)**

- **Source Document:** Ketika RC disetujui, nomor referensi RC (contoh: RC/04/2026/0001) harus tercatat pada _Source Document_ di dalam form _Goods Issue_.
- **Product Line Item:** Sistem akan memasukkan `Vehicle (Replacement)` ke dalam baris _Product_ pada form _Goods Issue_. Tipe produk ini harus dikenali sebagai barang yang dapat disimpan (_Storable Product_ / _Goods_).
- **Penentuan Nomor Seri:** Form _Goods Issue_ tidak bisa diselesaikan (_Done_) apabila petugas belum memasukkan Nomor Seri (_Serial Number_ / _Asset Number_) dari unit kendaraan pengganti fisik yang dikeluarkan.

### **D. Post-Condition (Validasi Pasca-Proses)**

- Mobil baru (pengganti) yang dikeluarkan melalui _Goods Issue_ otomatis berubah _Fleet Sub-Status_-nya menjadi **Replacement Car**.
- Mobil lama yang ditarik dari pelanggan dicatat kembali status ketersediaannya ke lokasi CRS melalui proses terpisah yaitu **BASTK Masuk**.

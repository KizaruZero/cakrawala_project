# BASTK Management

## 0.16 — Backdate BASTK

Tanggal Keluar dan Tanggal Masuk boleh diisi dengan tanggal lampau pada form,
import/API, dan popup Submit Out/In. Popup mempertahankan tanggal dokumen yang
sudah diisi, termasuk tanggal lampau; jika kosong tetap default hari ini.

Validasi urutan tanggal, checklist, tanda tangan, stock/picking, invoice lunas,
dan pembatasan edit berdasarkan status tetap berlaku. Tidak mengubah tanggal
Accounting Date maupun jurnal yang sudah ada. Upgrade modul setelah deployment
agar pembatasan tanggal di date picker juga diperbarui.

### Pengujian

Suite `TestBastkBackdate` mencakup create/edit tanggal lampau, Submit Out/In,
default popup, urutan tanggal, tanda tangan, dan opsi date picker.
Instalasi baru lokal saat ini memiliki kendala terpisah pada XPath
`mobility_card` di `x_stock_asset_receipt/views/fleet_vehicle_views.xml`.
Suite diuji memakai salinan modul tersebut di direktori QA dengan selector
kompatibilitas, tanpa mengubah kode Fleet pada repository atau data staging.

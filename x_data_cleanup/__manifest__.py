{
    'name': 'Data Cleanup (Pre-Production)',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Bersihkan data transaksi dengan preview dependensi, cascade aman, dan reset sequence',
    'description': """
Data Cleanup
============
Membersihkan data transaksi dari database staging/test sebelum dipakai sebagai
database production, tanpa menyentuh master data dan konfigurasi.

* Klasifikasi model: Transaksi / Master / Perlu Review (bisa diatur).
* Grafik relasi dibaca langsung dari foreign key PostgreSQL, jadi addon custom
  ikut tercakup otomatis.
* Preview lengkap: jumlah record per tabel, referensi yang dikosongkan, dokumen
  lain yang ikut terdampak, dan simulasi (dry-run) yang di-rollback.
* Hapus per record dari list view asli (Action > Data Cleanup) beserta
  turunannya, atau hapus semua transaksi sekaligus.
* Semua-atau-tidak-sama-sekali: kalau satu tabel gagal, tidak ada yang terhapus.
* Reset sequence, kosongkan lock date, sesuaikan stok, reset status fleet.
* Pengaman: hanya Administrator, harus dibuka kuncinya per database (berlaku
  terbatas waktu), konfirmasi dengan nama database, dan log permanen.

Ambil backup sebelum menjalankan. Uninstall addon ini sebelum database
dipakai sebagai production.
""",
    'author': 'Cakrawala',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/cleanup_target_views.xml',
        'views/cleanup_link_views.xml',
        'views/cleanup_log_views.xml',
        'wizard/cleanup_wizard_views.xml',
        'wizard/sequence_wizard_views.xml',
        'views/cleanup_dashboard_views.xml',
        'views/menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
}

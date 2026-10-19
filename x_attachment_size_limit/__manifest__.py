{
    'name': 'Batas Ukuran Attachment',
    'version': '19.0.1.0.1',
    'summary': 'Tolak file upload yang melebihi batas ukuran, yang bisa diatur dari General Settings',
    'description': """
Menerapkan satu batas ukuran maksimal untuk semua file yang diupload user:
field Binary (disimpan sebagai attachment), chatter, Documents, import, dll.

* Batas diatur dalam MB di Settings > General Settings > Attachment, dan disimpan
  di system parameter standar ``web.max_file_upload_size``, sehingga pengecekan
  bawaan web client sebelum upload memakai nilai yang sama.
* Pengecekan dilakukan di create/write ``ir.attachment`` berdasarkan ukuran file
  asli (sebelum Odoo memperkecil gambar berukuran besar).
* Hanya upload yang terjadi dalam HTTP request yang dicek: cron, email masuk,
  dan PDF report yang dibuat sistem tidak pernah ditolak.
    """,
    'category': 'Hidden/Tools',
    'license': 'LGPL-3',
    'depends': ['base_setup', 'mail'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}

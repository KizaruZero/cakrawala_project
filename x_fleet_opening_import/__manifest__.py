{
    'name': 'Fleet Opening Import',
    'version': '19.0.1.0.0',
    'category': 'Fleet Custom',
    'summary': 'Import unit kendaraan awal sekaligus: Fleet Number (SN), Analytic, Fleet, dan stok',
    'description': """
Satu file Excel, satu baris per unit. Per baris dibuat (atau dipakai ulang bila sudah ada):
Fleet Number (stock.lot), Analytic Account (Asset Number = Fleet Number), Fleet Vehicle yang
terhubung ke keduanya, dan stok qty 1 di lokasinya (inventory adjustment langsung di-apply).

File dicek dulu tanpa menyimpan apa pun. Import bersifat semua-atau-tidak-sama-sekali:
satu baris error, tidak ada yang masuk, dan errornya ditampilkan per baris.
""",
    'author': 'Cakrawala',
    'license': 'LGPL-3',
    'depends': ['stock', 'fleet', 'account', 'x_stock_asset_receipt', 'x_fleet_document'],
    'external_dependencies': {'python': ['openpyxl', 'xlsxwriter']},
    'data': [
        'security/ir.model.access.csv',
        'views/fleet_opening_import_views.xml',
    ],
    'installable': True,
    'application': False,
}

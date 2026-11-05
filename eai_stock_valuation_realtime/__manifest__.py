# Copyright 2026 Xapiens for PT Emas Antam Indonesia
# License OPL-1 (internal project module)
{
    'name': 'EAI - Real-time Stock Valuation',
    'version': '19.0.1.0.2',
    'summary': 'Jurnal persediaan per stock move dengan akun interim Stock Input/Output, '
               'khusus kategori produk yang ditandai',
    'description': """
Valuasi Persediaan Real-time per Stock Move
===========================================

Mengembalikan perilaku valuasi real-time gaya Odoo 17 (akun interim Stock Input /
Stock Output) **hanya untuk kategori produk yang ditandai**. Kategori lain tetap
100% perilaku standar Odoo 19.

* Vendor bill   : Dr Stock Input / Cr AP
* Receipt       : Dr Stock / Cr Stock Input
* Retur beli    : Dr Piutang Klaim + Dr/Cr Selisih Harga / Cr Stock (rata-rata)
* Credit note   : Dr AP / Cr Piutang Klaim (qty diretur) atau Stock Input
* Delivery      : Dr Stock Output / Cr Stock
* Invoice final : Dr HPP / Cr Stock Output (nilai DO)
* Retur jual, opname, scrap, revaluasi: dijurnal dari nilai stock move
* Stock Closing (Inventory Valuation > Close) mengecualikan kategori bertanda
* Landed cost pada receipt kategori bertanda dijurnal sebagai delta nilai receipt

Lihat dokumen spec-addon-valuasi-realtime-v1.x.md.
""",
    'author': 'Xapiens',
    'category': 'Accounting/Accounting',
    'depends': ['stock_account', 'purchase_stock', 'sale_stock', 'stock_landed_costs'],
    'data': [
        'security/ir.model.access.csv',
        'security/eai_rt_security.xml',
        'views/product_category_views.xml',
        'views/res_config_settings_views.xml',
        'views/stock_warehouse_views.xml',
        'views/stock_move_views.xml',
        'views/account_move_views.xml',
        'report/eai_rt_balance_report_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
}

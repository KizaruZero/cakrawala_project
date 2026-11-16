# -*- coding: utf-8 -*-
{
    'name': 'Report Insentif Marketing',
    'version': '19.0.1.0.0',
    'category': 'Sales/Rental',
    'summary': 'Laporan insentif marketing per unit dari Rental Order Line dan RPC',
    'description': """
Laporan insentif marketing per unit.

- Sumber unit: Rental Order Line yang berasal dari RPC dan sudah punya Actual Delivery.
- Angka insentif diambil dari RPC (Jumlah Insentif sesuai Harga Sewa Final,
  dibagi Jumlah Unit). Modul ini tidak mengubah RPC maupun konfigurasinya.
- Unit EV (Fuel Type = Electric di Fleet) mendapat 80% insentif.
- Angka disimpan di tabel laporan sendiri saat data diambil, sehingga tidak
  berubah bila konfigurasi RPC diubah kemudian.
""",
    'author': 'Xapiens Teknologi Indonesia',
    'website': 'https://xapiens.id',
    'license': 'LGPL-3',
    'depends': [
        'sale_renting',
        'fleet',
        'x_stock_asset_receipt',
        'x_sale_purchase_custom',
        'x_rental_profit_calculation',
    ],
    'data': [
        'security/marketing_incentive_security.xml',
        'security/ir.model.access.csv',
        'data/ir_config_parameter_data.xml',
        'views/marketing_incentive_line_views.xml',
        'wizard/marketing_incentive_generate_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
}

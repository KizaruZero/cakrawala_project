# -*- coding: utf-8 -*-
{
    'name': 'Laporan Laba Rugi Kendaraan',
    'version': '19.0.1.0.5',
    'category': 'Accounting/Reporting',
    'summary': 'Laporan Laba Rugi per unit kendaraan berdasarkan Akun Analitik dan Armada',
    'description': """
Laporan Laba Rugi Kendaraan
===========================
Laporan Laba Rugi per unit kendaraan berdasarkan akun analitik, GL entries, leasing schedule, dan amortisasi aset.
Menu: Accounting > Reporting > Laporan Laba Rugi Kendaraan
    """,
    'author': 'Cakrawala',
    'depends': [
        'base',
        'account',
        'fleet',
        'x_fleet_document',
        'x_leasing_amortization',
    ],
    'data': [
        'security/ir.model.access.csv',
        'report/vehicle_pnl_report_templates.xml',
        'wizard/vehicle_pnl_wizard_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}

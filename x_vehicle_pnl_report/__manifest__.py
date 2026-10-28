# -*- coding: utf-8 -*-
{
    'name': 'Vehicle PnL Report',
    'version': '19.0.1.0.3',
    'category': 'Accounting/Reporting',
    'summary': 'Vehicle Profit and Loss Report by Analytic Account and Fleet',
    'description': """
Vehicle PnL Report
==================
Laporan Laba Rugi per unit kendaraan berdasarkan akun analitik, GL entries, leasing schedule, dan amortisasi aset.
Menu: Accounting > Reporting > PnL Report
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

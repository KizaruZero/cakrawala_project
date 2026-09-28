{
    'name': 'SPK Invoice Integration',
    'author': 'Cakrawala',
    'version': '1.1',
    'category': 'Fleet Custom',
    'summary': 'Create Invoice from SPK',
    'depends': ['account', 'purchase', 'x_spk', 'x_bak'],
    'data': [
        'security/spk_invoice_security.xml',
        'security/ir.model.access.csv',
        'views/fleet_spk_views_inherit.xml',
        'views/account_move_views.xml',
        'reports/account_move_report_templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

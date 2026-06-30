{
    'name': 'SPK Invoice Integration',
    'version': '1.0',
    'category': 'Fleet Custom',
    'summary': 'Create Invoice from SPK',
    'depends': ['account', 'x_spk'],
    'data': [
        'security/spk_invoice_security.xml',
        'security/ir.model.access.csv',
        'views/fleet_spk_views_inherit.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

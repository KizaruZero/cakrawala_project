{
    'name': 'Accounting - Leaseback Integration',
    'version': '1.0',
    'category': 'Accounting',
    'summary': 'Integration of Leaseback with Incoming Payment & Purchase Order',
    'depends': ['account', 'purchase', 'account_asset'],
    'data': [
        'views/account_asset_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

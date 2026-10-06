{
    'name': 'Payment & Receive Voucher',
    'version': '19.0.1.3.1',
    'summary': 'Sequential authorization before vendor and customer payments',
    'category': 'Accounting/Accounting',
    'author': 'Payment Voucher Contributors',
    'license': 'LGPL-3',
    'depends': ['account', 'mail'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/rules.xml',
        'data/sequences.xml',
        'views/config_views.xml',
        'views/voucher_views.xml',
        'wizards/decision_views.xml',
        'views/account_move_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'payment_receive_voucher/static/src/js/voucher_list_buttons.js',
            'payment_receive_voucher/static/src/xml/voucher_list_buttons.xml',
        ],
    },
    'installable': True,
    'application': False,
}

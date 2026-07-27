{
    'name': 'Customer Statement of Account',
    'summary': 'Create and email a Statement of Account from selected invoices',
    'version': '19.0.1.0.10',
    'category': 'Accounting/Accounting',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/soa_email_wizard_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
}

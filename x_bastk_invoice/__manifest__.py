{
    'name': 'BASTK Invoice Integration',
    'version': '1.0',
    'category': 'Custom',
    'summary': 'Create Invoice from BASTK',
    'depends': ['account', 'x_bastk_management'],
    'data': [
        'views/bastk_management_views_inherit.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

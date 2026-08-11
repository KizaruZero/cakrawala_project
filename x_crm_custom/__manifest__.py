{
    'name': 'CRM Custom Fleet',
    'version': '19.0.1.0.1',
    'category': 'Sales/CRM',
    'summary': 'Custom CRM adjustments for Fleet business flow',
    'author': 'Odoo Developer',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'crm',
        'fleet',
        'sale_crm',
        'sale_renting_crm',
        'base_address_extended',
        'x_rental_profit_calculation',
        'x_sale_purchase_custom',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/crm_master_menus.xml',
        'views/crm_lead_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'x_crm_custom/static/src/js/archive_blocking.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

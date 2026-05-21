{
    'name': 'CRM Custom Fleet',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Custom CRM adjustments for Fleet business flow',
    'author': 'Odoo Developer',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'crm',
        'fleet',
        'base_address_extended',  # often contains res.city depending on setup, but base_address_city is merged into base in recent versions.
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/crm_master_menus.xml',
        'views/crm_lead_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

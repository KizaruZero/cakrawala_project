{
    'name': "x_email_notification",

    'summary': "Email Notification",
    'category': 'Fleet Custom',
    'description': """
Email Notification for Fleet
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'version': '0.1',
    'license': 'LGPL-3',
    'application': False,
    'installable': True,

    # any module necessary for this one to work correctly
    'depends': ['base', 'fleet', 'mail'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/notification_template_views.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}


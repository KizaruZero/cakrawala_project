{
    'name': "x_fleet_gr",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Fleet Custom',
    'version': '19.0.1.0.3',

    # any module necessary for this one to work correctly
    'depends': ['base', 'fleet', 'account', 'analytic', 'mail', 'x_stock_asset_receipt', 'x_email_notification'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/fleet_document_expiry_notification_cron.xml',
        'views/fleet_vehicle_sub_type_views.xml',
        'views/inherite_templates.xml',
        'views/fleet_vehicle_plate_history_views.xml',
        'views/account_payment_register_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'x_fleet_document/static/src/js/archive_blocking.js',
        ],
    },
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}


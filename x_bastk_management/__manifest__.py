{
    'name': "x_bastk_management",

    'summary': "BASTK Management",

    'description': """
BASTK Management:
- Define BASTK types
- Define BASTK checklists
- Define BASTK lines
- Define BASTK records
    """,

    'author': "Kizaru Kaede",
    'website': "https://www.kizarukaede.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Fleet Custom',
    'version': '0.7',
    'license': 'LGPL-3',


    # any module necessary for this one to work correctly
    'depends': ['base', 'mail', 'fleet', 'stock', 'sale_stock', 'analytic', 'x_fleet_document', 'x_email_notification'],

    'assets': {
        'web.assets_backend': [
            'x_bastk_management/static/src/scss/bastk_checklist.scss',
            'x_bastk_management/static/src/js/image_annotator.js',
            'x_bastk_management/static/src/xml/image_annotator.xml',
            'x_bastk_management/static/src/js/analytic_distribution_fleet_domain.js',
        ],
    },

    # always loaded
    'data': [
        'security/bastk_security.xml',
        'data/ir_sequence_data.xml',
        'data/bastk_notification_cron.xml',
        'security/ir.model.access.csv',
        'wizard/bastk_picking_wizard_views.xml',
        'wizard/bastk_submit_wizard_views.xml',
        'views/bastk_views.xml',
        'views/bastkl_type_views.xml',
        'views/asset_type_views.xml',
        'views/fleet_category_views.xml',
        'views/stock_picking_views.xml',
        'views/bastk_master_description_views.xml',
        'views/sale_order_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/templates.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'application': True,
    'installable': True,
}



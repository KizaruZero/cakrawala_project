{
    'name': 'Replacement Car',
    'version': '1.0',
    'summary': 'Fleet Replacement Car Management',
    'category': 'Fleet Custom',
    'depends': [
        'fleet',
        'x_service_planning',
        'x_spk',
        'x_fleet_document',
        'x_stock_asset_receipt',
        'x_bastk_management',
    ],
    "assets": {    
        "web.assets_backend": [
            "x_replacement_car/static/src/js/replacement_car_form.js",
            ],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        "report/rc_report.xml",
        'views/replacement_car_views.xml',
        'views/bastk_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/fleet_spk_views.xml',
        'views/stock_picking_views.xml',
    ],

    'installable': True,
    'application': True,
}
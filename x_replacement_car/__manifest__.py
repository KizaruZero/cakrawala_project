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
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/replacement_car_views.xml',
        'views/fleet_spk_views.xml',
        'views/stock_picking_views.xml',
        "report/rc_report.xml",
    ],

    'installable': True,
    'application': True,
}
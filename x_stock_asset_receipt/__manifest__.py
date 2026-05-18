# -*- coding: utf-8 -*-
{
    'name': 'X_Stock_Asset_Receipt',
    'version': '1.0',
    'category': 'Fleet Custom',
    'summary': 'Enhancements for Goods Receive with Asset and Leasing fields',
    'description': """
        This module adds custom fields to the Goods Receive (stock.picking) and operations (stock.move)
        to handle Asset tracking (License Plate, Chassis No, Engine No) and Leasing (Rental Type).
        It also provides a button to auto-generate Serial Numbers for received assets.
    """,
    'depends': ['stock', 'purchase', 'fleet'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/vehicle_substatus_data.xml',
        'views/stock_picking_views.xml',
        'views/stock_move_line_views.xml',
        'views/stock_lot_views.xml',
        'views/product_template_views.xml',
        'views/ir_sequence_views.xml',
        'views/vehicle_substatus_views.xml',
        'views/fleet_vehicle_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'x_stock_asset_receipt/static/src/scss/stock_picking.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}

{
    "name": "Inventory Enhance",
    "license": "LGPL-3",
    "version": "1.0.2",
    "summary": "Restrict Inventory Overview by Operation Type allowed users",
    "category": "Inventory/Inventory",
    "author": "Custom",
    "depends": ["stock", "purchase", "purchase_stock", "stock_picking_batch"],
    "data": [
        "security/stock_operation_type_rules.xml",
        "security/stock_operation_type_rules_bypass.xml",
        "views/stock_picking_type_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
    "post_init_hook": "post_init_hook",
    "assets": {
        "web.assets_backend": [
            "x_inventory_enhance/static/src/js/archive_blocking.js",
        ],
    },
}

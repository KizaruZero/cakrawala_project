{
    "name": "Inventory Enhance",
    "version": "1.0",
    "summary": "Restrict Inventory Overview by Operation Type allowed users",
    "category": "Inventory/Inventory",
    "author": "Custom",
    "depends": ["stock"],
    "data": [
        "security/stock_operation_type_rules.xml",
        "data/stock_picking_type_data.xml",
        "views/stock_picking_type_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}

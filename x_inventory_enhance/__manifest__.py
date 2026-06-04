{
    "name": "Inventory Enhance",
    "version": "1.0.1",
    "summary": "Restrict Inventory Overview by Operation Type allowed users",
    "category": "Inventory/Inventory",
    "author": "Custom",
    "depends": ["stock"],
    "data": [
        "security/stock_operation_type_rules.xml",
        "security/stock_operation_type_rules_bypass.xml",
        "views/stock_picking_type_views.xml",
    ],
    "installable": True,
    "application": False,
    "post_init_hook": "post_init_hook",
}

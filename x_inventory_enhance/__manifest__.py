{
    "name": "Inventory Enhance",
    "version": "1.0",
    "summary": "Restrict Inventory Overview by Operation Type allowed users",
    "category": "Inventory/Inventory",
    "author": "Custom",
    "depends": ["stock"],
    "data": [
        "security/stock_operation_type_rules.xml",
        "views/stock_picking_type_views.xml",
    ],
    "installable": True,
    "application": False,
}

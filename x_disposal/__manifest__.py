{
    "name": "x_disposal",
    "version": "1.0.2",
    "summary": "Module for vehicle disposal bidding",
    "description": "Manages disposal bidding and prepares approval flow (follow x_spk).",
    "category": "Fleet Custom",
    "author": "Auto-generated",
    "depends": ["base", "fleet", "mail", "sale_stock", "x_stock_asset_receipt", "x_fleet_document", "x_spk"],
    "assets": {    
        "web.assets_backend": [
            "x_disposal/static/src/js/disposal_bidding_form.js",
            ],
    },
    "data": [
        "security/ir.model.access.csv",
        "data/disposal_sequence.xml",
        "data/disposal_approval_matrix_data.xml",
        "report/disposal_report_templates.xml",
        "views/disposal_approval_matrix_views.xml",
        "views/disposal_approval_action_wizard_views.xml",
        "views/disposal_views.xml",
        "views/disposal_menus.xml",
    ],
    "installable": True,
    "application": True,
}

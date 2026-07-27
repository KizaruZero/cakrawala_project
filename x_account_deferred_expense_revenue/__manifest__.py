{
    "name": "Deferred Expense and Revenue",
    "summary": "Deferred expense and revenue automation for Odoo 19",
    "version": "19.0.1.0.4",
    "category": "Accounting/Accounting",
    "author": "Codex",
    "license": "LGPL-3",
    "depends": ["account", "accountant", "mail", "purchase"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/account_deferred_model_views.xml",
        "views/account_deferred_entry_views.xml",
        "views/account_account_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
}

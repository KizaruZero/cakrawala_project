{
    "name": "X_Asset Leaseback",
    "version": "19.0.1.0.0",
    "summary": "Leaseback disposal for fixed assets (Sell without an invoice)",
    "description": """
Adds a "Leaseback" action next to Dispose / Sell / Re-evaluate / Pause in the
asset modification wizard.

Unlike a Sell, a Leaseback does not require a customer invoice: the user simply
inputs an A/R Account and an A/R Amount. The disposal journal entry follows the
native Sell logic, but the whole gain/loss versus the asset Book Value is booked
to a single Deferred Profit/Loss account (e.g. 501409 Laba Rugi Ditangguhkan):

    Cr  Asset account            (original value)
    Dr  Accumulated Depreciation (depreciated to date)
    Dr  A/R Account              (A/R Amount)
    Cr/Dr Deferred Profit/Loss   (gain -> credit, loss -> debit)

The transaction is recorded in the Asset History just like a Sell.
""",
    "author": "Custom (Cakrawala)",
    "category": "Accounting/Accounting",
    "depends": ["account_asset"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/asset_modify_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}

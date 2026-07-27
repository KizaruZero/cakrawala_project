{
    "name": "X_Asset Leaseback",
    "version": "19.0.1.0.0",
    "summary": "Leaseback disposal and integration with Incoming Payment & Purchase Order",
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

After the asset is closed, users can create an Incoming Payment or Purchase Order
from the asset form. Both actions redirect to the respective form for manual input,
and the reference/status are tracked on the Other Info tab.
""",
    "author": "Custom (Cakrawala)",
    "category": "Accounting/Accounting",
    "depends": ["account_asset", "purchase"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/asset_modify_views.xml",
        "views/account_asset_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}

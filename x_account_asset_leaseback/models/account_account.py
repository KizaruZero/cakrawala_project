from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = "account.account"

    is_ar_account = fields.Boolean(
        string="Is AR Account",
        help="Make this account selectable as the A/R Account of an asset leaseback.",
    )
    is_deferred_pl_account = fields.Boolean(
        string="Is Deferred Profit/Loss Account",
        help="Make this account selectable as the Deferred Profit/Loss Account of an "
        "asset leaseback (e.g. 501409 Laba Rugi Ditangguhkan).",
    )

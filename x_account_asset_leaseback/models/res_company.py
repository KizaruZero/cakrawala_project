from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    leaseback_deferred_account_id = fields.Many2one(
        "account.account",
        check_company=True,
        string="Leaseback Deferred Profit/Loss Account",
        help="Account used to book the gain/loss of a leaseback against the asset "
        "book value (e.g. 501409 Laba Rugi Ditangguhkan).",
    )

    def _get_leaseback_deferred_account(self):
        """Return the deferred P/L account for a leaseback.

        Falls back to the account whose code is ``501409`` when the company
        setting has not been filled in yet, so existing databases work out of
        the box.
        """
        self.ensure_one()
        if self.leaseback_deferred_account_id:
            return self.leaseback_deferred_account_id
        return self.env["account.account"].with_company(self).search(
            [
                *self.env["account.account"]._check_company_domain(self),
                ("code", "=", "501409"),
            ],
            limit=1,
        )

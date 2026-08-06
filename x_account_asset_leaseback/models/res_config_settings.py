from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    leaseback_deferred_account_id = fields.Many2one(
        related="company_id.leaseback_deferred_account_id",
        readonly=False,
        string="Leaseback Deferred Profit/Loss Account",
    )

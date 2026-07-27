from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    asset_id = fields.Many2one("account.asset", string="Asset Link")

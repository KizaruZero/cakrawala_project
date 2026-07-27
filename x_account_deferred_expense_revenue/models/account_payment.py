from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    deferred_entry_id = fields.Many2one("account.deferred.entry", string="Deferred Entry Link")

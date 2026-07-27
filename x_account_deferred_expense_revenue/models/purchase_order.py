from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    deferred_entry_id = fields.Many2one("account.deferred.entry", string="Deferred Entry Link")

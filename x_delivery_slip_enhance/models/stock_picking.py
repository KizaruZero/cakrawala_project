from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    received_by = fields.Many2one(
        "res.users",
        string="Received By",
        domain=[("share", "=", False)],
        tracking=True,
    )

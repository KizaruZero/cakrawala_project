from odoo import models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        # NOTE: Goods Issue has been removed from Replacement Car, so the previous logic
        # linking stock.picking to replacement.car via good_issue_id has been disabled.
        return super().button_validate()
        
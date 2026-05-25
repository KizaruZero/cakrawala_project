from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    replacement_car = fields.Boolean(
        string='Replacement Car',
        readonly=True,
        copy=False,
        default=False,
        help='Otomatis dicentang saat Delivery Order (DO) berstatus Done.'
    )
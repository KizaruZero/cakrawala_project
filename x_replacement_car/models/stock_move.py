from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    replacement_car = fields.Boolean(
        string='Replacement Car',
        compute='_compute_replacement_car',
        store=True,
        readonly=True,
        copy=False,
        default=False
    )

    @api.depends('state')
    def _compute_replacement_car(self):
        for rec in self:
            rec.replacement_car = rec.state == 'done'
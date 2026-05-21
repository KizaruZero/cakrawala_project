from odoo import models, fields

class ReplacementCarLine(models.Model):
    _name = 'replacement.car.line'
    _description = 'Replacement Car Line'

    replacement_car_id = fields.Many2one(
        'replacement.car',
        string='Replacement Car',
        required=True,
        ondelete='cascade'
    )

    selected = fields.Boolean(
        string='Select'
    )

    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )

    quantity = fields.Float(
        string='Qty',
        default=1
    )

    price_unit = fields.Float(
        string='Unit Price'
    )
from odoo import api, models, fields

class FleetContractProductLine(models.Model):
    _name = 'fleet.contract.product.line'
    _description = 'Fleet Contract Product Line'

    contract_id = fields.Many2one(
        'fleet.vehicle.log.contract',
        string="Contract",
        ondelete='cascade',
        required=True
    )

    product_id = fields.Many2one(
        'product.product',
        string="Product",
        required=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        default=lambda self: self.env.company.currency_id
    )

    estimated_price = fields.Monetary(
        string="Estimated Price",
        currency_field='currency_id'
    )
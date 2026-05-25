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

    quantity = fields.Float(
        string='Qty',
        default=1
    )

    price_unit = fields.Float(
        string='Unit Price'
    )

    selected = fields.Boolean(
        string='Select',
        default=False
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

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string="Analytic"
    )

    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        if self.contract_id and self.contract_id.vehicle_id and self.contract_id.vehicle_id.analytic_account_id:
            self.analytic_account_id = self.contract_id.vehicle_id.analytic_account_id
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SaleOrderInputLine(models.Model):
    _name = 'sale.order.input.line'
    _description = 'Rental / Sale Order Input Line'
    _order = 'order_id, sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    order_id = fields.Many2one('sale.order', string='Order Reference', required=True, ondelete='cascade', index=True, copy=False)
    product_id = fields.Many2one(
        'product.product', string='Product',
        domain="[('sale_ok', '=', True)]", required=True
    )
    name = fields.Text(string='Description', required=True)
    quantity = fields.Float(string='Quantity', default=1.0, required=True)
    generated_qty = fields.Float(string='Generated Qty', default=0.0, readonly=True, copy=False)
    price_unit = fields.Float(string='Unit Price/Month', required=True, digits='Product Price')
    estimated_delivery_date = fields.Date(string='Estimated Delivery')
    tax_ids = fields.Many2many('account.tax', string='Taxes', domain="[('type_tax_use','=','sale')]")

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id:
            return
        if not self.name:
            self.name = self.product_id.get_product_multiline_description_sale()
        if self.price_unit == 0.0:
            self.price_unit = self.product_id.list_price
        if not self.tax_ids and self.order_id:
            self.tax_ids = self.product_id.taxes_id.filtered(lambda t: t.company_id == self.order_id.company_id)

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("Quantity in Input Order must be strictly greater than 0."))
            if line.quantity < line.generated_qty:
                raise ValidationError(_("You cannot set Quantity (%s) lower than what has already been generated (%s). Please use 'Reset Order' if you need to reduce generated quantity.") % (line.quantity, line.generated_qty))

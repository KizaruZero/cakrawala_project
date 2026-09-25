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
    currency_id = fields.Many2one(
        related='order_id.currency_id',
        readonly=True,
    )
    price_subtotal = fields.Monetary(
        string='Subtotal',
        currency_field='currency_id',
        compute='_compute_amount',
    )
    price_tax = fields.Monetary(
        string='Tax',
        currency_field='currency_id',
        compute='_compute_amount',
    )
    price_total = fields.Monetary(
        string='Total',
        currency_field='currency_id',
        compute='_compute_amount',
    )

    def _prepare_base_line_for_taxes_computation(self, **kwargs):
        self.ensure_one()
        company = self.order_id.company_id or self.env.company
        base_values = {
            'tax_ids': self.tax_ids,
            'price_unit': self.price_unit,
            'quantity': self.quantity,
            'product_id': self.product_id,
            'partner_id': self.order_id.partner_id,
            'currency_id': self.order_id.currency_id or company.currency_id,
            'rate': self.order_id.currency_rate,
        }
        base_values.update(kwargs)
        return self.env['account.tax']._prepare_base_line_for_taxes_computation(
            self, **base_values
        )

    @api.depends(
        'quantity', 'price_unit', 'tax_ids',
        'order_id.currency_id', 'order_id.currency_rate',
        'order_id.company_id', 'order_id.partner_id',
    )
    def _compute_amount(self):
        account_tax = self.env['account.tax']
        for line in self:
            company = line.order_id.company_id or self.env.company
            base_line = line._prepare_base_line_for_taxes_computation()
            account_tax._add_tax_details_in_base_line(base_line, company)
            account_tax._round_base_lines_tax_details([base_line], company)
            tax_details = base_line['tax_details']
            line.price_subtotal = tax_details['total_excluded_currency']
            line.price_total = tax_details['total_included_currency']
            line.price_tax = line.price_total - line.price_subtotal

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

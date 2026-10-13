from odoo import api, fields, models
from odoo.tools.float_utils import float_compare


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    fixed_discount = fields.Float(
        string="Fixed Disc.",
        digits="Product Price",
        default=0.0,
        help="Fixed discount amount carried from the purchase order line.",
    )
    fixed_discount_type = fields.Selection(
        selection=[('percentage', 'Percentage'), ('fixed', 'Fixed Amount')],
        string="Discount Input Type",
        default='percentage',
        copy=True,
        help="Technical field tracking which discount value should remain authoritative when price or quantity changes.",
    )

    @api.onchange('discount')
    def _onchange_bill_discount_to_fixed(self):
        for line in self:
            if not line._is_vendor_document_line():
                continue
            gross = line.price_unit * line.quantity
            if line.fixed_discount_type == 'fixed' and gross and line.fixed_discount:
                precision = line.env['decimal.precision'].precision_get('Discount')
                equivalent_percentage = line.fixed_discount / gross * 100.0
                if float_compare(line.discount, equivalent_percentage, precision_digits=precision) == 0:
                    continue
            line.fixed_discount_type = 'percentage'
            line.fixed_discount = line.currency_id.round(gross * line.discount / 100.0) if gross and line.discount else 0.0

    @api.onchange('fixed_discount')
    def _onchange_bill_fixed_to_percentage(self):
        for line in self:
            if not line._is_vendor_document_line():
                continue
            gross = line.price_unit * line.quantity
            if line.fixed_discount_type == 'percentage' and gross:
                percentage_amount = line.currency_id.round(gross * line.discount / 100.0) if line.discount else 0.0
                if line.currency_id.is_zero(line.fixed_discount - percentage_amount):
                    continue
            line.fixed_discount_type = 'fixed'
            line.discount = (line.fixed_discount / gross * 100.0) if gross and line.fixed_discount else 0.0

    @api.onchange('price_unit', 'quantity')
    def _onchange_bill_price_or_quantity(self):
        for line in self:
            if not line._is_vendor_document_line():
                continue
            gross = line.price_unit * line.quantity
            if line.fixed_discount_type == 'fixed':
                line.discount = (line.fixed_discount / gross * 100.0) if gross and line.fixed_discount else 0.0
            else:
                line.fixed_discount = line.currency_id.round(gross * line.discount / 100.0) if gross and line.discount else 0.0

    def _is_vendor_document_line(self):
        self.ensure_one()
        return self.move_id.move_type in ('in_invoice', 'in_refund', 'in_receipt')

    def _uses_fixed_discount_amount(self):
        self.ensure_one()
        return self.fixed_discount_type == 'fixed' or bool(self.fixed_discount and not self.discount)

    @api.depends('quantity', 'discount', 'price_unit', 'tax_ids', 'currency_id', 'amount_currency', 'fixed_discount')
    def _compute_totals(self):
        return super()._compute_totals()

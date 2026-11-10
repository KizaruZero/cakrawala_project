import math

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


def _validate_other_cost_amount(value):
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        raise ValidationError(_('Biaya Lain-Lain harus berupa nominal positif atau nol.'))
    if not math.isfinite(amount) or amount < 0:
        raise ValidationError(_('Biaya Lain-Lain harus berupa nominal positif atau nol.'))


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
    other_cost_deduction = fields.Monetary(
        string='Biaya Lain-Lain', currency_field='currency_id', default=0,
        help='Potongan sekali per baris setelah diskon dan sebelum pajak, dalam mata uang bill.',
    )

    @api.constrains('other_cost_deduction', 'quantity', 'price_unit', 'discount',
                    'fixed_discount', 'fixed_discount_type', 'tax_ids', 'display_type', 'move_id')
    def _check_other_cost_deduction(self):
        for line in self:
            line._validate_other_cost_input()
            if not line.other_cost_deduction:
                continue
            base = line.move_id._prepare_product_base_line_for_taxes_computation(line)
            self.env['account.tax']._add_tax_details_in_base_line(base, line.company_id)
            if line.currency_id.compare_amounts(base['tax_details']['raw_total_excluded_currency'], 0) < 0:
                raise ValidationError(_('Biaya Lain-Lain tidak boleh melebihi subtotal setelah diskon sebelum pajak.'))

    def _validate_other_cost_input(self):
        self.ensure_one()
        _validate_other_cost_amount(self.other_cost_deduction)
        if self.other_cost_deduction:
            if not self._is_vendor_document_line() or self.display_type != 'product':
                raise ValidationError(_('Biaya Lain-Lain hanya berlaku pada baris produk vendor bill/credit note.'))
            if self.quantity <= 0:
                raise ValidationError(_('Quantity harus lebih besar dari nol jika Biaya Lain-Lain diisi.'))

    @api.model_create_multi
    def create(self, values_list):
        for values in values_list:
            _validate_other_cost_amount(values.get(
                'other_cost_deduction', self.env.context.get('default_other_cost_deduction', 0)))
        return super().create(values_list)

    def write(self, values):
        if 'other_cost_deduction' in values:
            _validate_other_cost_amount(values['other_cost_deduction'])
            for line in self:
                if line.move_id.state != 'draft' and line.other_cost_deduction != values['other_cost_deduction']:
                    raise UserError(_('Biaya Lain-Lain hanya dapat diubah pada bill Draft.'))
        return super().write(values)

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

    @api.depends('quantity', 'discount', 'price_unit', 'tax_ids', 'currency_id', 'amount_currency',
                 'fixed_discount', 'fixed_discount_type', 'other_cost_deduction')
    def _compute_totals(self):
        return super()._compute_totals()

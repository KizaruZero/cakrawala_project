from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_round

class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    fixed_discount = fields.Float(string="Fixed Disc.", digits="Product Price", default=0.0)

    @api.depends('product_qty', 'price_unit', 'tax_ids', 'discount', 'fixed_discount')
    def _compute_amount(self):
        return super()._compute_amount()
    

    @api.onchange("discount", "price_unit", "product_qty")
    def _onchange_discount_update_fixed(self):
        for line in self:
            if line.discount:
                base_total = line.price_unit * line.product_qty
                calc_fixed = base_total * (line.discount / 100.0)
                current_perc = (line.fixed_discount / base_total) * 100.0 if base_total else 0.0
                if abs(line.discount - current_perc) > 0.01:
                    line.fixed_discount = calc_fixed
            else:
                line.fixed_discount = 0.0

    @api.onchange("fixed_discount", "price_unit", "product_qty")
    def _onchange_fixed_discount_update_perc(self):
        for line in self:
            base_total = line.price_unit * line.product_qty
            if line.fixed_discount and base_total > 0:
                calc_disc = (line.fixed_discount / base_total) * 100.0
                if abs(line.discount - calc_disc) > 0.01:
                    line.discount = calc_disc
            elif not line.fixed_discount:
                line.discount = 0.0

    def _prepare_base_line_for_taxes_computation(self):
        base_line = super()._prepare_base_line_for_taxes_computation()
        if self.fixed_discount:
            qty = base_line.get('quantity', 1.0) or 1.0
            base_line['discount'] = 0.0
            base_line['price_unit'] = self._price_unit_after_fixed_discount(qty)
        return base_line

    def _price_unit_after_fixed_discount(self, quantity=None):
        self.ensure_one()
        quantity = quantity if quantity is not None else self.product_qty
        if not quantity:
            return self.price_unit
        return (self.price_unit * quantity - self.fixed_discount) / quantity

    def _uses_exact_fixed_discount(self):
        """True only when the amount is independent of the stored percentage."""
        self.ensure_one()
        if not self.fixed_discount or not self.product_qty:
            return False
        percentage_amount = self.price_unit * self.product_qty * self.discount / 100.0
        return not self.currency_id.is_zero(self.fixed_discount - percentage_amount)

    def _prepare_account_move_line(self, move=False):
        values = super()._prepare_account_move_line(move=move)
        if self.fixed_discount and self.product_qty:
            bill_currency = move.currency_id if move else self.currency_id
            date = (move and move.date) or fields.Date.today()
            fixed_mode = self._uses_exact_fixed_discount()
            values.update({
                'discount': self.discount,
                'fixed_discount': self.currency_id._convert(
                    self.fixed_discount * abs(self.qty_to_invoice) / self.product_qty,
                    bill_currency, self.company_id, date, round=False,
                ),
                'fixed_discount_type': 'fixed' if fixed_mode else 'percentage',
            })

            if fixed_mode and 'balance' in values:
                net_unit_price = self._price_unit_after_fixed_discount()
                net_total = self.tax_ids.with_context(round=False, round_base=False).compute_all(
                    net_unit_price,
                    currency=self.currency_id,
                    quantity=abs(self.qty_to_invoice),
                    product=self.product_id,
                    partner=self.order_id.partner_id,
                )['total_excluded']
                values['balance'] = self.currency_id._convert(
                    net_total, self.company_id.currency_id, self.company_id,
                    date, round=False,
                )
        return values

    def _get_stock_move_price_unit(self):
        self.ensure_one()
        if not self._uses_exact_fixed_discount():
            return super()._get_stock_move_price_unit()
        order = self.order_id
        price_unit = self._price_unit_after_fixed_discount()
        price_unit_prec = self.env['decimal.precision'].precision_get('Product Price')
        if self.tax_ids:
            qty = self.product_qty or 1
            price_unit = self.tax_ids.compute_all(
                price_unit,
                currency=order.currency_id,
                quantity=qty,
                product=self.product_id,
                partner=order.partner_id,
                rounding_method="round_globally",
            )['total_void'] / qty
        if self.product_uom_id.id != self.product_id.uom_id.id:
            price_unit = price_unit / self.product_uom_id.factor * self.product_id.uom_id.factor
        if order.currency_id != order.company_id.currency_id:
            conversion_date = self.env.context.get('conversion_date', self.date_order) or fields.Date.today()
            price_unit = order.currency_id._convert(
                price_unit, order.company_id.currency_id, self.company_id,
                conversion_date, round=False,
            )
        return float_round(price_unit, precision_digits=price_unit_prec)

    @api.constrains('discount', 'fixed_discount', 'price_unit', 'product_qty')
    def _check_discounts(self):
        for line in self:
            if line.discount > 100.0:
                raise ValidationError("Percentage discount cannot exceed 100%.")
            if line.discount < 0.0:
                raise ValidationError("Percentage discount cannot be negative.")
            base_total = line.price_unit * line.product_qty
            if line.fixed_discount > base_total:
                raise ValidationError("Fixed discount cannot exceed the line's gross amount.")
            if line.fixed_discount < 0.0:
                raise ValidationError("Fixed discount cannot be negative.")

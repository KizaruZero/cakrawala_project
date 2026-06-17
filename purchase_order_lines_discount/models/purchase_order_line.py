from odoo import api, fields, models
from odoo.exceptions import ValidationError

class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    fixed_discount = fields.Float(string="Fixed Disc.", digits="Product Price", default=0.0)
    
    # We remove the re-definition of `discount` because it's already a native field in Odoo's purchase.order.line.
    # Odoo native discount handles subtotal computation automatically.

    @api.onchange("discount", "price_unit", "product_qty")
    def _onchange_discount_update_fixed(self):
        for line in self:
            if line.discount:
                base_total = line.price_unit * line.product_qty
                calc_fixed = base_total * (line.discount / 100.0)
                current_perc = (line.fixed_discount / base_total) * 100.0 if base_total else 0.0
                # Prevent cyclic overwriting due to float rounding (threshold 0.01%)
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
            # Bypass the percentage discount rounding issue entirely by injecting 
            # the exact fixed discount mathematically into the unit price before tax engine computes.
            qty = base_line.get('quantity', 1.0) or 1.0
            base_line['discount'] = 0.0
            base_line['price_unit'] = (self.price_unit * qty - self.fixed_discount) / qty
        return base_line

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

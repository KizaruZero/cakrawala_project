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
                line.fixed_discount = base_total * (line.discount / 100.0)
            else:
                line.fixed_discount = 0.0

    @api.onchange("fixed_discount", "price_unit", "product_qty")
    def _onchange_fixed_discount_update_perc(self):
        for line in self:
            base_total = line.price_unit * line.product_qty
            if line.fixed_discount and base_total > 0:
                # Update the native discount field, which automatically triggers Odoo's native _compute_amount logic
                line.discount = (line.fixed_discount / base_total) * 100.0
            elif not line.fixed_discount:
                line.discount = 0.0

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

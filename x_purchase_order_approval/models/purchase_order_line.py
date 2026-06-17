# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    line_no = fields.Char(string='Line No')
    remark = fields.Char(string='Remark')
    price_unit_max = fields.Float(
        string='Max Unit Price',
        digits='Product Price',
        copy=False,
        help='Highest allowed unit price for this line (from purchase request / initial price after pricelist). '
             'You may lower the unit price but not raise it above this amount.',
    )
    product_qty_max = fields.Float(
        string='Max Quantity',
        digits='Product Unit of Measure',
        copy=False,
        help='Highest allowed quantity for this line (from purchase request). '
             'You may lower the quantity but not raise it above this amount.',
    )

    def _price_unit_max_rounding(self):
        prec = self.env['decimal.precision'].precision_get('Product Price')
        return 10 ** -prec if prec else 0.0001

    def _sync_price_unit_max_after_pricelist(self):
        """Raise ceiling to the effective unit price if Odoo computed a higher vendor price than the PR estimate."""
        rounding = self._price_unit_max_rounding()
        for line in self:
            if float_is_zero(line.price_unit_max, precision_rounding=rounding):
                continue
            if float_compare(line.price_unit, line.price_unit_max, precision_rounding=rounding) > 0:
                line.write({'price_unit_max': line.price_unit})

    @api.constrains('price_unit', 'price_unit_max')
    def _check_price_unit_max(self):
        rounding = self._price_unit_max_rounding()
        for line in self:
            if float_is_zero(line.price_unit_max, precision_rounding=rounding):
                continue
            if float_compare(line.price_unit, line.price_unit_max, precision_rounding=rounding) > 0:
                raise ValidationError(
                    _('Unit price for "%(product)s" cannot exceed purchase request unit estimate price :  %(max)s (current: %(current)s).') % {
                        'product': line.product_id.display_name,
                        'max': line.price_unit_max,
                        'current': line.price_unit,
                    }
                )

    @api.constrains('product_qty', 'product_qty_max', 'requisition_line_id')
    def _check_product_qty_max(self):
        rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure') or 0.001
        for line in self:
            if getattr(line, 'requisition_line_id', False):
                all_po_lines = self.env['purchase.order.line'].search([
                    ('requisition_line_id', '=', line.requisition_line_id.id),
                    ('state', '!=', 'cancel')
                ])
                total_ordered = sum(all_po_lines.mapped('product_qty'))
                if float_compare(total_ordered, line.requisition_line_id.quantity, precision_rounding=rounding) > 0:
                    other_ordered = sum((all_po_lines - line).mapped('product_qty'))
                    allowed_qty = line.requisition_line_id.quantity - other_ordered
                    raise ValidationError(
                        _('Quantity for "%(product)s" exceeds the purchase request remaining quantity! (Max allowed: %(allowed)s, You entered: %(current)s).') % {
                            'product': line.product_id.display_name,
                            'allowed': max(0.0, allowed_qty),
                            'current': line.product_qty,
                        }
                    )
            elif getattr(line, 'product_qty_max', False) and not float_is_zero(line.product_qty_max, precision_rounding=rounding):
                if float_compare(line.product_qty, line.product_qty_max, precision_rounding=rounding) > 0:
                    raise ValidationError(
                        _('Quantity for "%(product)s" cannot exceed purchase request quantity :  %(max)s (current: %(current)s).') % {
                            'product': line.product_id.display_name,
                            'max': line.product_qty_max,
                            'current': line.product_qty,
                        }
                    )
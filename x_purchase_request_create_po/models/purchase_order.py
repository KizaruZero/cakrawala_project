from odoo import models, fields, api
from odoo.exceptions import ValidationError

class PurchaseOrderInherit(models.Model):
    _inherit = 'purchase.order'

    # Example of adding a new field
    requisition_order_ids = fields.Many2many('employee.purchase.requisition', string='Purchase Requests', readonly=True)

    def button_submit_purchase_order(self):
        res = super(PurchaseOrderInherit, self).button_submit_purchase_order()
        for order in self:
            for line in order.order_line:
                if line.requisition_line_id:
                    line.requisition_line_id._compute_ordered_remaining_qty()
        return res
    
    def unlink(self):
        for rec in self:
            requisition_line_ids = rec.mapped('order_line.requisition_line_id')
            res = super(PurchaseOrderInherit, self).unlink()
            for requisition_line in requisition_line_ids:
                requisition_line._compute_ordered_remaining_qty()
        return res

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.constrains('product_qty', 'requisition_line_id')
    def _check_pr_qty_limit(self):
        for line in self:
            if line.requisition_line_id:
                other_po_lines = self.env['purchase.order.line'].search([
                    ('requisition_line_id', '=', line.requisition_line_id.id),
                    ('state', '!=', 'cancel'),
                    ('id', '!=', line.id)
                ])
                other_qty = sum(other_po_lines.mapped('product_qty'))
                total_qty = other_qty + line.product_qty
                
                # Use a simple float comparison to avoid any precision rounding issues
                if round(total_qty, 3) > round(line.requisition_line_id.quantity, 3):
                    raise ValidationError(
                        "Quantity for '%(product)s' exceeds the purchase request remaining quantity! (Max allowed: %(max_allowed)s, You entered: %(current)s)." % {
                            'product': line.product_id.display_name,
                            'max_allowed': line.requisition_line_id.quantity - other_qty,
                            'current': line.product_qty,
                        }
                    )

    # Example of adding a new field
    requisition_id = fields.Many2one('employee.purchase.requisition', string='Purchase Request', readonly=True)
    requisition_line_id = fields.Many2one('requisition.order', string='Purchase Request Line', readonly=True)

    def unlink(self):
        line_ids = self.mapped('requisition_line_id')
        res = super(PurchaseOrderLine, self).unlink()
        line_ids._compute_ordered_remaining_qty()
        line_ids.purchase_ids = [(3, line.id) for line in line_ids.purchase_ids]
        return res
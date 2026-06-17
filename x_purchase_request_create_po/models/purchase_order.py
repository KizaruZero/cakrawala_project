from odoo import models, fields

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

    # Example of adding a new field
    requisition_id = fields.Many2one('employee.purchase.requisition', string='Purchase Request', readonly=True)
    requisition_line_id = fields.Many2one('requisition.order', string='Purchase Request Line', readonly=True)

    def unlink(self):
        line_ids = self.mapped('requisition_line_id')
        res = super(PurchaseOrderLine, self).unlink()
        line_ids._compute_ordered_remaining_qty()
        line_ids.purchase_ids = [(3, line.id) for line in line_ids.purchase_ids]
        return res
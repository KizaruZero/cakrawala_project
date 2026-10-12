from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class PurchaseOrderInherit(models.Model):
    _inherit = 'purchase.order'

    # Example of adding a new field
    requisition_order_ids = fields.Many2many('employee.purchase.requisition', string='Purchase Requests', readonly=True)
    input_line_ids = fields.One2many('purchase.order.input.line', 'order_id', string='Input Orders', copy=False)
    has_pending_input_order = fields.Boolean(compute='_compute_input_order_status')
    has_generated_input_order = fields.Boolean(compute='_compute_input_order_status')

    @api.depends('input_line_ids.quantity', 'input_line_ids.generated_qty')
    def _compute_input_order_status(self):
        for order in self:
            order.has_pending_input_order = any(line._pending_qty() > 0 for line in order.input_line_ids)
            order.has_generated_input_order = bool(order.input_line_ids.generated_line_ids)

    def _check_input_order_generated(self):
        for order in self:
            if order.has_pending_input_order:
                raise ValidationError(_("Purchase Order %s still has fleet items in Input Order that are not generated into Order Lines yet. Please click 'Generate Order Lines' first.") % order.name)

    def action_generate_order_lines(self):
        """Split every Input Order item into 1-unit order lines (only the units not generated yet)."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Order Lines can only be generated while the Purchase Order is in RFQ state."))
        if not self.input_line_ids:
            raise UserError(_("No items found in Input Order to generate."))

        vals_list = []
        for input_line in self.input_line_ids:
            vals_list += [input_line._prepare_purchase_order_line_vals() for _i in range(int(input_line._pending_qty()))]
        if not vals_list:
            raise UserError(_("All items in Input Order have already been generated. Use 'Reset Order Lines' if you need to clear and regenerate."))

        new_lines = self.env['purchase.order.line'].create(vals_list)
        # menghitung harga satuan, tanggal plan, dan nama barang — sama seperti saat PO dibuat dari PR
        for line_purchase in new_lines:
            line_purchase._compute_price_unit_and_date_planned_and_name()
        new_lines._sync_price_unit_max_after_pricelist()
        request_lines = self.input_line_ids.requisition_line_id
        request_lines._compute_ordered_remaining_qty()
        request_lines._sync_purchase_links()
        return True

    def action_reset_order_lines(self):
        """Delete the order lines generated from Input Order so they can be generated again."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("You can only reset Order Lines while the Purchase Order is in RFQ state."))
        generated_lines = self.input_line_ids.generated_line_ids
        if not generated_lines:
            raise UserError(_("There are no Order Lines generated from Input Order to reset."))
        generated_lines.unlink()
        return True

    def button_submit_purchase_order(self):
        self._check_input_order_generated()
        res = super(PurchaseOrderInherit, self).button_submit_purchase_order()
        for order in self:
            for line in order.order_line:
                if line.requisition_line_id:
                    line.requisition_line_id._compute_ordered_remaining_qty()
        return res

    def button_confirm(self):
        self._check_input_order_generated()
        return super().button_confirm()

    def button_cancel(self):
        res = super().button_cancel()
        # Unit yang masih tertahan di Input Order PO batal harus kembali ke sisa PR
        self.input_line_ids.requisition_line_id._compute_ordered_remaining_qty()
        return res

    def unlink(self):
        requisition_line_ids = self.mapped('order_line.requisition_line_id') | self.mapped('input_line_ids.requisition_line_id')
        res = super(PurchaseOrderInherit, self).unlink()
        requisition_line_ids._compute_ordered_remaining_qty()
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
    input_line_id = fields.Many2one('purchase.order.input.line', string='Input Order', readonly=True, copy=False, index='btree_not_null', ondelete='set null')

    def unlink(self):
        line_ids = self.mapped('requisition_line_id')
        res = super(PurchaseOrderLine, self).unlink()
        line_ids._compute_ordered_remaining_qty()
        line_ids._sync_purchase_links()
        return res

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_round


class PurchaseOrderInputLine(models.Model):
    """Fleet item of a PR-generated PO, waiting to be split into 1-unit lines.

    Same idea as ``sale.order.input.line`` on the Rental Order: the user keeps
    the requested quantity here and "Generate Order Lines" creates one PO line
    per unit, so every unit can later be matched to its own Fleet and
    Analytic Account on the Goods Receipt.

    ``generated_qty`` is counted from the PO lines that really exist rather
    than kept as a counter, so deleting a generated line (or Reset) frees
    exactly that unit for the next Generate.
    """
    _name = 'purchase.order.input.line'
    _description = 'Purchase Order Input Line'
    _order = 'order_id, sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    order_id = fields.Many2one('purchase.order', string='Order Reference', required=True, ondelete='cascade', index=True, copy=False)
    state = fields.Selection(related='order_id.state')
    currency_id = fields.Many2one(related='order_id.currency_id')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    name = fields.Text(string='Description', required=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unit')
    quantity = fields.Float(string='Quantity', digits='Product Unit', required=True, default=1.0)
    generated_qty = fields.Float(string='Generated Qty', digits='Product Unit', compute='_compute_generated_qty', store=True)
    price_unit = fields.Float(string='Unit Price', digits='Product Price')
    price_unit_max = fields.Float(string='Max Unit Price', digits='Product Price', help='Estimate price of the Purchase Request, carried to the generated lines.')
    price_subtotal = fields.Monetary(string='Subtotal', currency_field='currency_id', compute='_compute_price_subtotal')
    analytic_distribution = fields.Json(string='Analytic Distribution', help='Copied from the Purchase Request line to every generated line.')
    line_no = fields.Char(string='Line No')
    remark = fields.Char(string='Remark')
    requisition_id = fields.Many2one('employee.purchase.requisition', string='Purchase Request', readonly=True)
    requisition_line_id = fields.Many2one('requisition.order', string='Purchase Request Line', readonly=True, index=True)
    generated_line_ids = fields.One2many('purchase.order.line', 'input_line_id', string='Generated Order Lines')

    @api.depends('generated_line_ids.product_qty')
    def _compute_generated_qty(self):
        for line in self:
            line.generated_qty = sum(line.generated_line_ids.mapped('product_qty'))

    @api.depends('quantity', 'price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit

    def _pending_qty(self):
        """Units not generated into order lines yet."""
        self.ensure_one()
        return max(self.quantity - self.generated_qty, 0.0)

    @api.constrains('quantity', 'generated_qty')
    def _check_quantity(self):
        for line in self:
            if float_compare(line.quantity, 0.0, precision_digits=2) <= 0:
                raise ValidationError(_("Quantity in Input Order must be strictly greater than 0."))
            if float_compare(line.quantity, float_round(line.quantity, precision_digits=0), precision_digits=2) != 0:
                raise ValidationError(_("Quantity in Input Order must be a whole number: every fleet unit becomes its own order line."))
            if float_compare(line.quantity, line.generated_qty, precision_digits=2) < 0:
                raise ValidationError(_("You cannot set Quantity (%(qty)s) lower than what has already been generated (%(generated)s). Please use 'Reset Order Lines' if you need to reduce generated quantity.") % {
                    'qty': line.quantity,
                    'generated': line.generated_qty,
                })

    @api.constrains('quantity', 'requisition_line_id')
    def _check_pr_qty_limit(self):
        """Ordered units of a PR line — existing PO lines plus units still waiting
        in any Input Order — may never exceed what the PR line requested."""
        for line in self.filtered('requisition_line_id'):
            request_line = line.requisition_line_id
            po_lines = self.env['purchase.order.line'].search([
                ('requisition_line_id', '=', request_line.id),
                ('state', '!=', 'cancel'),
            ])
            input_lines = self.search([
                ('requisition_line_id', '=', request_line.id),
                ('order_id.state', '!=', 'cancel'),
            ])
            total_qty = sum(po_lines.mapped('product_qty')) + sum(input_line._pending_qty() for input_line in input_lines)
            if float_compare(total_qty, request_line.quantity, precision_digits=2) > 0:
                raise ValidationError(_("Quantity for '%(product)s' exceeds the purchase request remaining quantity! (Max allowed: %(max_allowed)s, You entered: %(current)s).") % {
                    'product': line.product_id.display_name,
                    'max_allowed': request_line.quantity - (total_qty - line.quantity),
                    'current': line.quantity,
                })

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.requisition_line_id._compute_ordered_remaining_qty()
        return lines

    def write(self, vals):
        if 'quantity' in vals and self.filtered(lambda line: line.state != 'draft'):
            raise UserError(_("Input Order can only be changed while the Purchase Order is in RFQ state."))
        res = super().write(vals)
        if 'quantity' in vals:
            self.requisition_line_id._compute_ordered_remaining_qty()
        return res

    def unlink(self):
        if self.filtered('generated_line_ids'):
            raise UserError(_("Cannot delete an Input Order line that already has generated Order Lines. Use 'Reset Order Lines' first."))
        request_lines = self.requisition_line_id
        res = super().unlink()
        request_lines._compute_ordered_remaining_qty()
        request_lines._sync_purchase_links()
        return res

    def _prepare_purchase_order_line_vals(self):
        """Values of ONE generated unit — same keys the PR -> PO flow uses."""
        self.ensure_one()
        return {
            'order_id': self.order_id.id,
            'input_line_id': self.id,
            'product_id': self.product_id.id,
            'name': self.name,
            'product_qty': 1.0,
            'product_qty_max': 1.0,
            'product_uom_id': self.product_uom_id.id or self.product_id.uom_id.id,
            'price_unit': self.price_unit,
            'price_unit_max': self.price_unit_max or self.price_unit,
            'analytic_distribution': self.analytic_distribution,
            'line_no': self.line_no,
            'remark': self.remark,
            'requisition_id': self.requisition_id.id,
            'requisition_line_id': self.requisition_line_id.id,
        }

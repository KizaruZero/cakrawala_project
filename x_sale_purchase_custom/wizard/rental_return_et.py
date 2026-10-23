from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class RentalReturnPickingET(models.TransientModel):
    _name = 'rental.return.picking.et'
    _description = 'Return Picking ET'

    order_id = fields.Many2one('sale.order', required=True, readonly=True, ondelete='cascade')
    line_ids = fields.One2many('rental.return.picking.et.line', 'wizard_id', string='Return ET Units')

    @api.model
    def default_get(self, names):
        values = super().default_get(names)
        if 'line_ids' in names and values.get('order_id'):
            order = self.env['sale.order'].browse(values['order_id']).exists()
            order.check_access('write')
            order._check_return_et_request_allowed()
            values['line_ids'] = [Command.create({'sale_line_id': line.id, 'quantity': 0})
                                  for line in order._get_return_et_eligible_lines()]
        return values

    def action_return_et(self):
        self.ensure_one()
        with self.env.cr.savepoint():
            return self._create_return_et_pickings()

    def _create_return_et_pickings(self):
        order = self.order_id
        order.check_access('write')
        order._lock_billing_engine_orders()
        order._check_return_et_request_allowed()
        order.order_line.invalidate_recordset(['qty_delivered', 'qty_returned', 'qty_returned_et', 'move_ids'])
        eligible = order._get_return_et_eligible_lines()
        if any(line.quantity < 0 for line in self.line_ids):
            raise UserError(_('Return ET quantities cannot be negative.'))
        selected = self.line_ids.filtered(lambda line: line.quantity > 0)
        if not selected:
            raise UserError(_('Please specify at least one non-zero Return ET quantity.'))
        if len(selected.sale_line_id) != len(selected):
            raise UserError(_('A Rental Order line can only be selected once.'))
        allocations = defaultdict(list)
        for line in selected:
            source = line.sale_line_id
            if source not in eligible or source.order_id != order:
                raise UserError(_('Only delivered, not-yet-returned units from this Rental Order can be returned ET.'))
            moves = order._get_return_et_move_quantities(source)
            available = sum(quantity for _move, quantity in moves)
            if float_compare(line.quantity, available, precision_rounding=source.product_uom_id.rounding) > 0:
                raise UserError(_('Return ET quantity exceeds the completed, returnable delivery quantity for %s.', source.product_id.display_name))
            remaining = line.quantity
            for move, quantity in moves:
                amount = min(remaining, quantity)
                if amount <= 0:
                    break
                allocations[move.picking_id.id].append({
                    'product_id': move.product_id.id, 'move_id': move.id,
                    'quantity': source.product_uom_id._compute_quantity(amount, move.product_uom),
                })
                remaining -= amount
        pickings = self.env['stock.picking']
        for picking_id, values in allocations.items():
            # The native factory retains sale links, return routes, reservation,
            # traceability and the normal confirm/assign/validate workflow.
            native = self.env['stock.return.picking'].with_context(
                active_model='stock.picking', active_id=picking_id, active_ids=[picking_id],
            ).create({
                'picking_id': picking_id,
                'product_return_moves': [Command.create(value) for value in values],
            })
            picking = native._create_return()
            picking.move_ids._mark_rental_return_et()
            pickings |= picking
        if not pickings:
            raise UserError(_('No completed Delivery Order is available for Return ET.'))
        order._register_return_et_request(selected.sale_line_id, pickings)
        action = {
            'name': _('Return ET Pickings'), 'type': 'ir.actions.act_window',
            'res_model': 'stock.picking', 'view_mode': 'list,form',
            'domain': [('id', 'in', pickings.ids)], 'target': 'current',
        }
        if len(pickings) == 1:
            action.update({'view_mode': 'form', 'res_id': pickings.id})
        return action


class RentalReturnPickingETLine(models.TransientModel):
    _name = 'rental.return.picking.et.line'
    _description = 'Return Picking ET Line'

    wizard_id = fields.Many2one('rental.return.picking.et', required=True, ondelete='cascade')
    sale_line_id = fields.Many2one('sale.order.line', required=True, readonly=True, ondelete='cascade')
    product_id = fields.Many2one(related='sale_line_id.product_id', readonly=True)
    license_plate = fields.Char(compute='_compute_return_details', string='License Plate')
    quantity = fields.Float(string='Quantity', digits='Product Unit', default=0, required=True)
    uom_id = fields.Many2one(related='sale_line_id.product_uom_id', readonly=True)
    available_quantity = fields.Float(compute='_compute_return_details', string='Returnable Quantity')

    @api.depends('sale_line_id', 'sale_line_id.move_ids.state', 'sale_line_id.move_ids.quantity')
    def _compute_return_details(self):
        for line in self:
            source = line.sale_line_id
            moves = line.wizard_id.order_id._get_return_et_move_quantities(source) if source else []
            line.available_quantity = sum(quantity for _move, quantity in moves)
            line.license_plate = (
                source._rental_invoice_license_plate()
                or ', '.join(filter(None, [getattr(move, 'initial_license_plate', '') for move, _qty in moves]))
            ) if source else False

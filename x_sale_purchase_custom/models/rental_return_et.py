from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    et_return_line_ids = fields.Many2many(
        'sale.order.line', 'sale_order_et_return_line_rel', 'order_id', 'line_id',
        string='Return ET Units', readonly=True, copy=False, check_company=True,
    )
    et_return_picking_ids = fields.Many2many(
        'stock.picking', 'sale_order_et_return_picking_rel', 'order_id', 'picking_id',
        string='Return ET Pickings', readonly=True, copy=False, check_company=True,
    )

    def _check_return_et_request_allowed(self):
        self.ensure_one()
        if not self.is_rental_order or self.state != 'sale':
            raise UserError(_('Return ET is only available for confirmed Rental Orders.'))
        # Old pending ET requests opened the tab without creating a return.
        # Allow those to enter the new wizard without resetting their data.
        if self.et_return_picking_ids or self.et_is_approved:
            raise UserError(_('Early Termination has already been requested for this Rental Order.'))

    def _get_return_et_eligible_lines(self):
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: not line.display_type and not line.is_downpayment
            and line.qty_delivered > 0 and line.qty_returned == 0 and line.qty_returned_et == 0
        )

    def _get_return_et_move_quantities(self, line):
        """Completed deliveries less all non-cancelled return reservations."""
        self.ensure_one()
        result = []
        for move in line.move_ids.sorted('id'):
            if (move.state != 'done' or move.scrap_id or move.location_dest_id.usage != 'customer'
                    or not move.picking_id or move.picking_id.company_id != self.company_id):
                continue
            returned = sum(
                returned.product_uom._compute_quantity(returned.product_uom_qty, move.product_uom)
                for returned in move.returned_move_ids if returned.state != 'cancel'
            )
            quantity = move.product_uom._compute_quantity(max(move.quantity - returned, 0), line.product_uom_id)
            if quantity > 0:
                result.append((move, quantity))
        return result

    def _return_et_penalty_amount(self, lines):
        self.ensure_one()
        # Use the actual unit's sale line, never just its product or a blank /
        # reused plate string. Grouped invoices contribute only selected units.
        rows = self.billing_engine_line_ids.filtered(lambda row: (
            row.sale_line_id in lines and (
                not row.invoice_id or row.invoice_id.state == 'draft'
                or row.invoice_id.state == 'posted' and row.invoice_id.payment_state == 'not_paid'
            )
        ))
        return self.currency_id.round(sum(rows.mapped('amount')) * 0.25)

    def _register_return_et_request(self, lines, pickings):
        self.ensure_one()
        self.write({
            'is_early_termination_requested': True,
            'et_return_line_ids': [Command.set(lines.ids)],
            'et_return_picking_ids': [Command.set(pickings.ids)],
            'et_penalty_amount': self._return_et_penalty_amount(lines),
            'et_termination_date': self.et_termination_date or fields.Date.context_today(self),
        })


class StockMove(models.Model):
    _inherit = 'stock.move'

    is_rental_return_et = fields.Boolean(string='Return ET', readonly=True, copy=False, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        if any(values.get('is_rental_return_et') for values in vals_list):
            raise UserError(_('Return ET classification is managed by the Return ET wizard.'))
        return super().create(vals_list)

    def write(self, values):
        if 'is_rental_return_et' in values:
            raise UserError(_('Return ET classification cannot be changed manually.'))
        return super().write(values)

    def _mark_rental_return_et(self):
        if any(move.state in ('done', 'cancel') or not move.origin_returned_move_id
               or not move.sale_line_id.order_id.is_rental_order for move in self):
            raise UserError(_('Only new Rental Order return moves can be marked as Return ET.'))
        super(StockMove, self).write({'is_rental_return_et': True})

    def _action_done(self, cancel_backorder=False):
        result = super()._action_done(cancel_backorder=cancel_backorder)
        lines = self.filtered('is_rental_return_et').sale_line_id
        if lines:
            # Run after native rental counters: ET must not also fill Returned.
            for name in ('qty_delivered', 'qty_returned', 'qty_returned_et'):
                self.env.add_to_compute(lines._fields[name], lines)
            lines._recompute_recordset(['qty_delivered', 'qty_returned', 'qty_returned_et'])
        return result

    def _create_backorder(self):
        et_sources = {
            (move.origin_returned_move_id.id, move.sale_line_id.id)
            for move in self if move.is_rental_return_et
        }
        result = super()._create_backorder()
        remaining_et = result.filtered(lambda move: (
            move.origin_returned_move_id.id, move.sale_line_id.id,
        ) in et_sources)
        if remaining_et:
            remaining_et._mark_rental_return_et()
        return result

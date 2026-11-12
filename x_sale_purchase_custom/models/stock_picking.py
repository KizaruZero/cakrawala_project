# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from markupsafe import Markup


import logging
_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    is_from_rental_order = fields.Boolean(
        related='sale_id.is_rental_order',
        string='Is from Rental Order',
        store=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        for picking in pickings:
            if picking.picking_type_id and picking.picking_type_code == 'outgoing':
                if not picking.picking_type_id.use_create_lots:
                    picking.picking_type_id.sudo().use_create_lots = True
                if not picking.picking_type_id.use_existing_lots:
                    picking.picking_type_id.sudo().use_existing_lots = True
        return pickings

    def button_validate(self):
        """Override to auto-fill actual_delivery_date on sale.order.line when DO is validated.

        A rental fleet unit takes it from its BASTK instead (Submit Out).
        """
        for picking in self:
            if picking.picking_type_id and picking.picking_type_code == 'outgoing':
                if not picking.picking_type_id.use_create_lots:
                    picking.picking_type_id.sudo().use_create_lots = True
                if not picking.picking_type_id.use_existing_lots:
                    picking.picking_type_id.sudo().use_existing_lots = True

        res = super().button_validate()

        for picking in self:
            if picking.picking_type_code == 'outgoing' and picking.state == 'done':
                for move in picking.move_ids:
                    if move.sale_line_id:
                        vals_to_write = {}
                        order = move.sale_line_id.order_id
                        follows_bastk = order.is_rental_order and move.product_id.is_vehicle
                        if not follows_bastk and not move.sale_line_id.actual_delivery_date:
                            vals_to_write['actual_delivery_date'] = order._get_local_date(picking.date_done)
                        
                        analytic_dist = False
                        analytic_account = False
                        for ml in move.move_line_ids:
                            if ml.lot_id and hasattr(ml.lot_id, 'analytic_account_id') and ml.lot_id.analytic_account_id:
                                analytic_account = ml.lot_id.analytic_account_id
                            elif hasattr(ml, 'analytic_account_id') and ml.analytic_account_id:
                                analytic_account = ml.analytic_account_id
                            if analytic_account:
                                break
                        if not analytic_account and hasattr(move, 'analytic_account_id') and move.analytic_account_id:
                            analytic_account = move.analytic_account_id
                                    
                        if analytic_account:
                            analytic_dist = {str(analytic_account.id): 100}
                            vals_to_write['analytic_distribution'] = analytic_dist

                        if vals_to_write:
                            move.sale_line_id.sudo().with_context(fleet_analytic_from_delivery=True).write(vals_to_write)


            elif picking.picking_type_code == 'incoming' and picking.state == 'done':
                # First, determine if this GR is linked to a Sales Order
                sale_order = False
                if hasattr(picking, 'purchase_id') and picking.purchase_id:
                    if hasattr(picking.purchase_id, 'sale_order_id') and picking.purchase_id.sale_order_id:
                        sale_order = picking.purchase_id.sale_order_id
                if sale_order:
                    picking._link_received_units_to_sale_order(sale_order)

        return res

    def _link_received_units_to_sale_order(self, sale_order):
        """Pair each unit received on this GR with a line of ``sale_order``.

        Units bought for a Sales Order are locked to it. A line whose delivery
        already holds the unit (reserved on Validate, see
        ``StockMove._trigger_assign``) takes it, otherwise the first line without
        a vehicle. The receipt is done whatever happens on the delivery side:
        what cannot be synced there is logged on the receipt, never raised.
        """
        self.ensure_one()
        problems = []
        waiting = []
        for ml in self.move_line_ids.filtered(lambda l: l.quantity > 0 and l.lot_id):
            analytic = False
            if hasattr(ml, 'analytic_account_id') and ml.analytic_account_id:
                analytic = ml.analytic_account_id
            elif hasattr(ml.lot_id, 'analytic_account_id') and ml.lot_id.analytic_account_id:
                analytic = ml.lot_id.analytic_account_id
            if not analytic:
                continue
            distribution = {str(analytic.id): 100}
            product_lines = sale_order.order_line.filtered(lambda l: l.product_id == ml.product_id)
            if product_lines.filtered(lambda l: l.analytic_distribution == distribution):
                continue
            free_lines = product_lines.filtered(lambda l: not l.analytic_distribution)
            holding_lines = free_lines.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
            ).move_line_ids.filtered(lambda l: l.lot_id == ml.lot_id)
            open_lines = product_lines.filtered(lambda l: any(m.state not in ('done', 'cancel') for m in l.move_ids))
            sale_line = holding_lines.move_id.sale_line_id[:1] or free_lines[:1] or open_lines[:1]
            if not sale_line:
                continue
            sale_line.sudo().with_context(fleet_analytic_from_delivery=True).write(
                {'analytic_distribution': distribution})
            try:
                with self.env.cr.savepoint():
                    if not self._sync_sale_line_deliveries(sale_line.sudo(), ml.lot_id, analytic):
                        waiting.append(Markup('<li>%s (%s)</li>') % (ml.lot_id.name, sale_line.name))
            except UserError as error:
                problems.append(_('%(lot)s (%(line)s): %(error)s',
                                  lot=ml.lot_id.name, line=sale_line.name, error=error.args[0]))
        if problems:
            self.message_post(body=Markup('%s<ul>%s</ul>') % (
                _('Received units were paired with %(order)s, but their delivery could not be '
                  'updated; reserve them on the delivery manually:', order=sale_order.name),
                Markup().join(Markup('<li>%s</li>') % problem for problem in problems),
            ))
        if waiting:
            self._notify_units_without_open_delivery(sale_order, waiting)

    def _notify_units_without_open_delivery(self, sale_order, units):
        """Tell, on the receipt and to whoever validates it, that paired units are not on a delivery yet."""
        if sale_order.state in ('draft', 'sent'):
            next_step = _('Fleet Number-nya otomatis masuk ke Delivery Order saat %(order)s di-Confirm.',
                          order=sale_order.name)
        else:
            next_step = _('Delivery Order-nya sudah Done atau Cancel: pilih unitnya di Delivery Order '
                          'secara manual bila nanti dikirim.')
        self.message_post(body=Markup('%s<ul>%s</ul>%s') % (
            _('Unit berikut sudah dipasangkan ke %(order)s, tapi barisnya belum punya Delivery Order '
              'yang terbuka:', order=sale_order.name),
            Markup().join(units), next_step,
        ))
        self.env.user._bus_send('simple_notification', {
            'type': 'warning',
            'title': _('%(receipt)s divalidasi', receipt=self.name),
            'message': _('%(count)s unit belum masuk Delivery Order %(order)s karena belum ada Delivery '
                         'Order yang terbuka. Detail di chatter.', count=len(units), order=sale_order.name),
        })

    def _sync_sale_line_deliveries(self, sale_line, lot, analytic):
        """Show the received unit on the open delivery of ``sale_line``.

        Returns False when the line has no open delivery to show it on.
        """
        out_moves = sale_line.move_ids.filtered(
            lambda m: m.picking_code == 'outgoing' and m.state not in ('done', 'cancel'))
        if not out_moves:
            # Quotation, delivery already done or cancelled: nothing to show the unit on.
            return False
        target = out_moves.move_line_ids.filtered(lambda l: l.lot_id == lot).move_id[:1] or out_moves[:1]
        if hasattr(target, '_prefill_fleet_unit'):
            # Unit data filled at quantity 0: the field team confirms the handover.
            target._prefill_fleet_unit(lot)
            return True
        for out_move in out_moves:
            if hasattr(out_move, 'analytic_account_id'):
                out_move.write({'analytic_account_id': analytic.id})
            for out_ml in out_move.move_line_ids:
                if hasattr(out_ml, 'analytic_account_id'):
                    out_ml.write({'analytic_account_id': analytic.id})
        return True


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _trigger_assign(self):
        """Units bought on a PO made for a Sales Order are locked to that order:
        reserve its deliveries first, before core offers the stock to any older
        delivery waiting for the same product."""
        deliveries = self.env['stock.move']
        auto_reserve = not self.env['ir.config_parameter'].sudo().get_param('stock.picking_no_auto_reserve')
        if auto_reserve and 'purchase_line_id' in self._fields:
            for move in self.filtered(lambda m: m.state == 'done' and m.picking_code == 'incoming'):
                sale_order = move.purchase_line_id.order_id.sale_order_id
                deliveries |= sale_order.order_line.move_ids.filtered(
                    lambda m: m.state in ('confirmed', 'partially_available')
                    and m.procure_method == 'make_to_stock'
                    and m.product_id == move.product_id
                    and move.location_dest_id._child_of(m.location_id)
                )
        if deliveries:
            deliveries.sorted(lambda m: (m.sale_line_id.sequence, m.sale_line_id.id, m.id))._action_assign()
        return super()._trigger_assign()


class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    @api.depends('picking_id')
    def _compute_moves_locations(self):
        super()._compute_moves_locations()
        for wizard in self.filtered(lambda item: item.picking_id.sale_id.is_rental_order):
            # An ET return already reserves these units, even before validation.
            wizard.product_return_moves = wizard.product_return_moves.filtered(
                lambda item: not item.move_id.returned_move_ids.filtered(
                    lambda move: move.is_rental_return_et and move.state != 'cancel'
                )
            )

    def _create_return(self):
        # Recheck on submit too: a standard popup may have been opened before
        # another user reserved its unit through Return ET.
        if any(line.quantity > 0 and line.move_id.sale_line_id.order_id.is_rental_order
               and line.move_id.returned_move_ids.filtered(
                   lambda move: move.is_rental_return_et and move.state != 'cancel'
               ) for line in self.product_return_moves):
            raise UserError(_('This unit already has a Return ET picking. Review that return before submitting another return.'))
        return super()._create_return()

#     @api.depends('picking_id')
#     def _compute_moves_locations(self):
#         super()._compute_moves_locations()
#         for wizard in self:
#             if wizard.product_return_moves:
#                 lines_to_remove = self.env['stock.return.picking.line']
#                 for line in wizard.product_return_moves:
#                     stock_move = line.move_id
#                     if not stock_move:
#                         continue
#                     
#                     # Compute returned qty
#                     returned_qty = 0.0
#                     for m in stock_move.move_dest_ids:
#                         if m.origin_returned_move_id == stock_move and m.state != 'cancel':
#                             # In Odoo 17, quantity is used instead of quantity_done
#                             returned_qty += getattr(m, 'quantity', getattr(m, 'product_uom_qty', 0.0))
#                     
#                     original_qty = getattr(stock_move, 'quantity', getattr(stock_move, 'product_uom_qty', 0.0))
#                     max_returnable = original_qty - returned_qty
#                     
#                     if max_returnable <= 0:
#                         lines_to_remove |= line
#                 
#                 if lines_to_remove:
#                     wizard.product_return_moves -= lines_to_remove

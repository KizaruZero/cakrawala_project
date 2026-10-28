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
        """Override to auto-fill actual_delivery_date on sale.order.line when DO is validated."""
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
                        if not move.sale_line_id.actual_delivery_date:
                            vals_to_write['actual_delivery_date'] = fields.Date.today()
                        
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
                    self._sync_sale_line_deliveries(sale_line.sudo(), ml.lot_id, analytic)
            except UserError as error:
                problems.append(_('%(lot)s (%(line)s): %(error)s',
                                  lot=ml.lot_id.name, line=sale_line.name, error=error.args[0]))
        if problems:
            self.message_post(body=Markup('%s<ul>%s</ul>') % (
                _('Received units were paired with %(order)s, but their delivery could not be '
                  'updated; reserve them on the delivery manually:', order=sale_order.name),
                Markup().join(Markup('<li>%s</li>') % problem for problem in problems),
            ))

    def _sync_sale_line_deliveries(self, sale_line, lot, analytic):
        """Move the open delivery of ``sale_line`` to the received unit."""
        out_moves = sale_line.move_ids.filtered(
            lambda m: m.picking_code == 'outgoing' and m.state not in ('done', 'cancel'))
        holding = out_moves.move_line_ids.filtered(lambda l: l.lot_id == lot)
        if hasattr(holding, '_sync_vehicle_fields_from_lot'):
            holding._sync_vehicle_fields_from_lot()
        if hasattr(sale_line, '_push_fleet_analytic_to_deliveries'):
            sale_line._push_fleet_analytic_to_deliveries()
            return
        for out_move in out_moves:
            if hasattr(out_move, 'analytic_account_id'):
                out_move.write({'analytic_account_id': analytic.id})
            for out_ml in out_move.move_line_ids:
                if hasattr(out_ml, 'analytic_account_id'):
                    out_ml.write({'analytic_account_id': analytic.id})


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

# -*- coding: utf-8 -*-
from odoo import models, fields, api


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


                for move in picking.move_ids:
                    if sale_order:
                        for ml in move.move_line_ids:
                            if ml.quantity <= 0:
                                continue

                            ml_analytic = False
                            if hasattr(ml, 'analytic_account_id') and ml.analytic_account_id:
                                ml_analytic = ml.analytic_account_id
                            elif hasattr(ml, 'lot_id') and ml.lot_id and hasattr(ml.lot_id, 'analytic_account_id') and ml.lot_id.analytic_account_id:
                                ml_analytic = ml.lot_id.analytic_account_id
                                
                            if ml_analytic:
                                ml_dist = {str(ml_analytic.id): 100}
                                
                                # Find an empty SO line for this product
                                empty_so_lines = sale_order.order_line.filtered(
                                    lambda l: l.product_id.id == ml.product_id.id and not l.analytic_distribution
                                )
                                if empty_so_lines:
                                    target_so_line = empty_so_lines[0]
                                    target_so_line.sudo().write({'analytic_distribution': ml_dist})
                                    
                                    # Sync to DO
                                    outgoing_moves = self.env['stock.move'].sudo().search([
                                        ('sale_line_id', '=', target_so_line.id),
                                        ('picking_type_id.code', '=', 'outgoing')
                                    ])
                                    for out_move in outgoing_moves:
                                        if hasattr(out_move, 'analytic_account_id'):
                                            out_move.sudo().write({'analytic_account_id': ml_analytic.id})
                                        if hasattr(out_move, 'x_spk_analytic_account_ids'):
                                            out_move.sudo().write({'x_spk_analytic_account_ids': [(4, ml_analytic.id)]})
                                        for out_ml in out_move.move_line_ids:
                                            if hasattr(out_ml, 'analytic_account_id'):
                                                out_ml.sudo().write({'analytic_account_id': ml_analytic.id})

        return res


class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

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

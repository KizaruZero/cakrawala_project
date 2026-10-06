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
            # Handle outgoing (DO) sync
            if picking.picking_type_code == 'outgoing':
                for move in picking.move_ids:
                    if move.sale_line_id:
                        vals_to_write = {}
                        if not move.sale_line_id.actual_delivery_date:
                            vals_to_write['actual_delivery_date'] = fields.Date.today()
                        
                        analytic_dist = False
                        analytic_account = False
                        if hasattr(move, 'analytic_account_id') and move.analytic_account_id:
                            analytic_account = move.analytic_account_id
                        else:
                            for ml in move.move_line_ids:
                                if hasattr(ml, 'analytic_account_id') and ml.analytic_account_id:
                                    analytic_account = ml.analytic_account_id
                                    break
                                    
                        if analytic_account:
                            analytic_dist = {str(analytic_account.id): 100}
                            vals_to_write['analytic_distribution'] = analytic_dist
                            
                            if hasattr(move.sale_line_id, 'purchase_line_ids') and move.sale_line_id.purchase_line_ids:
                                for po_line in move.sale_line_id.purchase_line_ids:
                                    po_line.sudo().write({'analytic_distribution': analytic_dist})

                        if vals_to_write:
                            move.sale_line_id.sudo().write(vals_to_write)

            # Handle incoming (GR) sync
            elif picking.picking_type_code == 'incoming':
                # First, determine if this GR is linked to a Sales Order
                sale_order = False
                if hasattr(picking, 'purchase_id') and picking.purchase_id:
                    if hasattr(picking.purchase_id, 'sale_order_id') and picking.purchase_id.sale_order_id:
                        sale_order = picking.purchase_id.sale_order_id

                for move in picking.move_ids:
                    # Collect all analytic accounts from all move lines for this product
                    analytic_accounts = []
                    for ml in move.move_line_ids:
                        if ml.qty_done <= 0:
                            continue
                        acc = False
                        if hasattr(ml, 'analytic_account_id') and ml.analytic_account_id:
                            acc = ml.analytic_account_id
                        elif hasattr(ml, 'lot_id') and ml.lot_id and hasattr(ml.lot_id, 'analytic_account_id') and ml.lot_id.analytic_account_id:
                            acc = ml.lot_id.analytic_account_id
                        
                        if acc and acc not in analytic_accounts:
                            analytic_accounts.append(acc)
                            
                    if analytic_accounts:
                        # Split percentage equally among all received vehicles for the PO line
                        pct = 100.0 / len(analytic_accounts)
                        po_analytic_dist = {str(acc.id): pct for acc in analytic_accounts}
                        
                        if hasattr(move, 'purchase_line_id') and move.purchase_line_id:
                            move.purchase_line_id.sudo().write({'analytic_distribution': po_analytic_dist})
                            
                            # Also sync to PR line if it exists
                            if hasattr(move.purchase_line_id, 'requisition_line_id') and move.purchase_line_id.requisition_line_id:
                                move.purchase_line_id.requisition_line_id.sudo().write({'analytic_distribution': po_analytic_dist})

                    # If we have an SO, we iterate all move lines to distribute their analytic accounts
                    # to the split SO lines (since PR might have grouped them)
                    if sale_order:
                        for ml in move.move_line_ids:
                            if ml.qty_done <= 0:
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

    @api.depends('picking_id')
    def _compute_moves_locations(self):
        super()._compute_moves_locations()
        for wizard in self:
            if wizard.product_return_moves:
                lines_to_keep = self.env['stock.return.picking.line']
                for line in wizard.product_return_moves:
                    stock_move = line.move_id
                    if not stock_move:
                        continue
                    
                    # Compute returned qty
                    returned_qty = 0.0
                    for m in stock_move.move_dest_ids:
                        if m.origin_returned_move_id == stock_move and m.state != 'cancel':
                            # In Odoo 17, quantity is used instead of quantity_done
                            returned_qty += getattr(m, 'quantity', getattr(m, 'product_uom_qty', 0.0))
                    
                    original_qty = getattr(stock_move, 'quantity', getattr(stock_move, 'product_uom_qty', 0.0))
                    max_returnable = original_qty - returned_qty
                    
                    if max_returnable > 0:
                        lines_to_keep |= line
                
                wizard.product_return_moves = lines_to_keep

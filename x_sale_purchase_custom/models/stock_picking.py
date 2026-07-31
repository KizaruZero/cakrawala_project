# -*- coding: utf-8 -*-
from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = 'stock.picking'

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
            # Only process outgoing deliveries (customer deliveries)
            if picking.picking_type_code != 'outgoing':
                continue

            # Get related sale order lines through stock moves
            for move in picking.move_ids:
                if move.sale_line_id and not move.sale_line_id.actual_delivery_date:
                    move.sale_line_id.actual_delivery_date = fields.Date.today()

        return res


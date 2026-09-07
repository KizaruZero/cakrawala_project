# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class CreatePoWizard(models.TransientModel):
    _name = 'create.po.wizard'
    _description = 'Create Purchase Order Wizard'

    sale_order_id = fields.Many2one('sale.order', string='Rental Order', required=True)
    partner_id = fields.Many2one('res.partner', string='Vendor (Dealer/Leasing)', required=True)

    def action_confirm(self):
        self.ensure_one()
        so = self.sale_order_id
        
        rpc = self.env['rpc.document'].search([('crm_lead_id', '=', so.opportunity_id.id)], order='id desc', limit=1)
        otr_leasing_val = rpc.otr_leasing if rpc else 0.0

        po_vals = {
            'partner_id': self.partner_id.id,
            'sale_order_id': so.id,
            'customer_so_related': so.partner_id.name,
            'rental_type_id': so.rental_type_id.id,
            'order_line': [(0, 0, {
                'product_id': line.product_id.id,
                'name': line.name,
                'product_qty': line.product_uom_qty,
                'product_uom_id': line.product_uom_id.id,
                'price_unit': otr_leasing_val if (otr_leasing_val > 0 and getattr(line.product_id, 'is_vehicle', False)) else line.price_unit,
            }) for line in so.order_line if line.product_id]
        }
        po = self.env['purchase.order'].create(po_vals)
        
        return {
            'name': _('Purchase Order'),
            'view_mode': 'form',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

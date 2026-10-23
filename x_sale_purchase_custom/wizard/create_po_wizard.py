# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class CreatePoWizard(models.TransientModel):
    _name = 'create.po.wizard'
    _description = 'Create Purchase Order Wizard'

    sale_order_id = fields.Many2one('sale.order', string='Rental Order', required=True)
    partner_id = fields.Many2one('res.partner', string='Vendor (Dealer/Leasing)', required=True)

    def _find_input_line(self, sale_line):
        """Input Order asal sebuah order line RO (Generate Order menyalin produk dan deskripsinya)."""
        input_lines = self.sale_order_id.input_line_ids.filtered(lambda l: l.product_id == sale_line.product_id)
        return input_lines.filtered(lambda l: l.name == sale_line.name)[:1] or input_lines[:1]

    def _prepare_po_line_vals(self, sale_line):
        input_line = self._find_input_line(sale_line)
        if input_line:
            harga_otr = input_line._get_rpc_harga_otr()
        else:
            harga_otr = self.sale_order_id._get_rpc_harga_otr(sale_line.product_id, sale_line.name)
        vals = {
            'product_id': sale_line.product_id.id,
            'name': sale_line.name,
            'product_qty': sale_line.product_uom_qty,
            'product_uom_id': sale_line.product_uom_id.id,
        }
        if harga_otr:
            vals.update({'price_unit': harga_otr, 'rpc_price_locked': True})
        return vals

    def action_confirm(self):
        self.ensure_one()
        so = self.sale_order_id
        po_vals = {
            'partner_id': self.partner_id.id,
            'sale_order_id': so.id,
            'customer_so_related': so.partner_id.name,
            'rental_type_id': so.rental_type_id.id,
            'x_notes': so.x_notes,
            'note': so.x_terms_conditions,
            'order_line': [
                (0, 0, self._prepare_po_line_vals(line))
                for line in so.order_line
                if line.product_id
            ],
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

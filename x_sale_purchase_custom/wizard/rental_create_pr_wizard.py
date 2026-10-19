# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class RentalCreatePRWizard(models.TransientModel):
    _name = 'rental.create.pr.wizard'
    _description = 'Wizard to Create Auto-Approved PR from Rental Order'

    def _default_vendor_id(self):
        return self.env['res.partner'].search([('is_general_vendor', '=', True)], limit=1)

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    vendor_id = fields.Many2one('res.partner', string='Vendor', required=True, default=_default_vendor_id)

    def _get_line_harga_otr(self, line, sale_order):
        """Retrieve Harga OTR for a rental order input line with intelligent fallbacks."""
        # 1. Direct harga_otr on the line
        if getattr(line, 'harga_otr', 0.0) and line.harga_otr > 0:
            return line.harga_otr

        # 2. Direct RPC document linked to the line
        rpc_line = getattr(line, 'rpc_document_id', False)
        if rpc_line:
            otr = rpc_line.harga_otr or rpc_line.purchase_harga_otr
            if otr and otr > 0:
                return otr

        # 3. Check RPC documents linked to the sale order (rpc_document_ids or rpc_document_id)
        rpc_docs = sale_order.rpc_document_ids or sale_order.rpc_document_id
        if rpc_docs:
            for rpc in rpc_docs:
                if rpc.name and rpc.name in (line.name or ''):
                    otr = rpc.harga_otr or rpc.purchase_harga_otr
                    if otr and otr > 0:
                        return otr
            for rpc in rpc_docs:
                if getattr(rpc, 'type_kendaraan_id', False) and rpc.type_kendaraan_id.id == line.product_id.id:
                    otr = rpc.harga_otr or rpc.purchase_harga_otr
                    if otr and otr > 0:
                        return otr
            if len(rpc_docs) == 1:
                otr = rpc_docs[0].harga_otr or rpc_docs[0].purchase_harga_otr
                if otr and otr > 0:
                    return otr

        # 4. Check CRM Lead / Opportunity linked to sale order
        if sale_order.opportunity_id:
            lead = sale_order.opportunity_id
            if getattr(lead, 'harga_otr', 0.0) and lead.harga_otr > 0:
                return lead.harga_otr
            lead_rpcs = getattr(lead, 'rpc_document_ids', False)
            if lead_rpcs:
                for rpc in lead_rpcs:
                    if rpc.name and rpc.name in (line.name or ''):
                        otr = rpc.harga_otr or rpc.purchase_harga_otr
                        if otr and otr > 0:
                            return otr
                if len(lead_rpcs) == 1:
                    otr = lead_rpcs[0].harga_otr or lead_rpcs[0].purchase_harga_otr
                    if otr and otr > 0:
                        return otr

        # 5. Check sale_order.harga_otr
        if getattr(sale_order, 'harga_otr', 0.0) and sale_order.harga_otr > 0:
            return sale_order.harga_otr

        # 6. Fallback to line.price_unit if no harga_otr is found
        return getattr(line, 'price_unit', 0.0)

    def action_confirm(self):
        self.ensure_one()
        sale_order = self.sale_order_id
        
        employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        if not employee:
            raise UserError(_("You must have a linked employee record to create a Purchase Request."))
            
        if not employee.department_id:
            raise UserError(_("The linked employee must have a Department/Division set to create a Purchase Request."))
            
        default_pr_type = self.env['purchase.request.type.master'].search([('is_default_value', '=', True)], limit=1)
        if not default_pr_type:
            raise UserError(_("Tidak ada PR Type yang di set sebagai default (is_default_value = True). Silakan atur terlebih dahulu di master data PR Type."))

        lines_to_process = sale_order.input_line_ids.filtered(lambda l: l.product_id)
        if not lines_to_process and sale_order.order_line:
            lines_to_process = sale_order.order_line.filtered(lambda l: l.product_id and not getattr(l, 'is_downpayment', False))

        pr_vals = {
            'sale_order_id': sale_order.id,
            'customer_so_related': sale_order.partner_id.name,
            'rental_type_id': sale_order.rental_type_id.id,
            'detail_description': sale_order.note,
            'employee_id': employee.id,
            'dept_id': employee.department_id.id,
            'department_id': employee.department_id.id,
            'user_id': self.env.uid,
            'internal_reference': sale_order.name,
            'purchase_request_type_id': default_pr_type.id,
            'partner_id': self.vendor_id.id,
            'state': 'approved',
            'requisition_order_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'description': line.name,
                'quantity': getattr(line, 'quantity', False) or getattr(line, 'product_uom_qty', 1.0),
                'remaining_qty': getattr(line, 'quantity', False) or getattr(line, 'product_uom_qty', 1.0),
                'estimate_price': self._get_line_harga_otr(line, sale_order),
                'uom_id': (line.product_id.uom_id.id if getattr(line, 'product_id', False) else False) or (getattr(line, 'product_uom_id', False).id if getattr(line, 'product_uom_id', False) else False),
            }) for line in lines_to_process]
        }
        
        pr = self.env['employee.purchase.requisition'].create(pr_vals)
        
        return {
            'name': _('Purchase Request'),
            'view_mode': 'form',
            'res_model': 'employee.purchase.requisition',
            'res_id': pr.id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

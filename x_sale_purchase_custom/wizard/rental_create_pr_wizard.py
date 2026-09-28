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
                'quantity': line.product_uom_qty,
                'remaining_qty': line.product_uom_qty,
                'estimate_price': line.price_unit,
                'uom_id': line.product_uom_id.id,
            }) for line in sale_order.order_line if line.product_id]
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

# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    rental_type_id = fields.Many2one('sale.rental.type', string='Rental Type')
    rental_type_id_is_related_pr = fields.Boolean(related='rental_type_id.is_related_pr')
    rental_type_id_is_related_po = fields.Boolean(related='rental_type_id.is_related_po')
    
    pr_related_ids = fields.One2many('employee.purchase.requisition', 'sale_order_id', string='PR Related')
    po_related_ids = fields.One2many('purchase.order', 'sale_order_id', string='PO Related')

    pr_related_html = fields.Html(compute='_compute_pr_po_html', string='PR Related')
    po_related_html = fields.Html(compute='_compute_pr_po_html', string='PO Related')

    @api.depends('pr_related_ids', 'po_related_ids')
    def _compute_pr_po_html(self):
        for order in self:
            pr_links = []
            for pr in order.pr_related_ids:
                url = f"/web#id={pr.id}&model=employee.purchase.requisition&view_type=form"
                pr_links.append(f"<a href='{url}' class='o_form_uri'>{pr.name}</a>")
            order.pr_related_html = "<span>" + ", ".join(pr_links) + "</span>" if pr_links else ""

            po_links = []
            for po in order.po_related_ids:
                url = f"/web#id={po.id}&model=purchase.order&view_type=form"
                po_links.append(f"<a href='{url}' class='o_form_uri'>{po.name}</a>")
            order.po_related_html = "<span>" + ", ".join(po_links) + "</span>" if po_links else ""

    def action_confirm(self):
        if self.env.context.get('x_disposal_skip_rental_type_check'):
            return super(SaleOrder, self).action_confirm()
        for order in self:
            if not order.rental_type_id:
                raise UserError(_("Please select a Rental Type before confirming the order."))
        return super(SaleOrder, self).action_confirm()

    def action_create_pr(self):
        self.ensure_one()
        # Find employee linked to current user
        employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        if not employee:
            raise UserError(_("You must have a linked employee record to create a Purchase Request."))
            
        if not employee.department_id:
            raise UserError(_("The linked employee must have a Department/Division set to create a Purchase Request."))
            
        # Create PR logic
        pr_vals = {
            'sale_order_id': self.id,
            'customer_so_related': self.partner_id.name,
            'rental_type_id': self.rental_type_id.id,
            'employee_id': employee.id,
            'dept_id': employee.department_id.id,
            'department_id': employee.department_id.id,
            'user_id': self.env.uid,
            'internal_reference': self.name,
            # For testing, we might need a default employee or let it compute. 
            # Assuming employee_id is required or has default.
            'requisition_order_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'description': line.name,
                'quantity': line.product_uom_qty,
                'estimate_price': line.price_unit,
            }) for line in self.order_line if line.product_id]
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

    def action_create_po(self):
        self.ensure_one()
        # Create PO logic
        po_vals = {
            'partner_id': self.partner_id.id, # Placeholder, user needs to change this usually to vendor
            'sale_order_id': self.id,
            'customer_so_related': self.partner_id.name,
            'rental_type_id': self.rental_type_id.id,
            'order_line': [(0, 0, {
                'product_id': line.product_id.id,
                'name': line.name,
                'product_qty': line.product_uom_qty,
                'product_uom_id': line.product_uom_id.id,
                'price_unit': line.price_unit,
            }) for line in self.order_line if line.product_id]
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

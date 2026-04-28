# -*- coding: utf-8 -*-

import logging
from datetime import datetime
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)

class EmployeePurchaseRequisitionInherit(models.Model):
    _inherit = 'employee.purchase.requisition'

    purchase_order_ids = fields.Many2many('purchase.order', string='Purchase Orders', compute='_get_purchase_order_ids')
    active = fields.Boolean(string='Active', default=True)
    active_create_po = fields.Boolean(string='Active Create PO', default=True, compute='_compute_active_create_po')

    def _compute_active_create_po(self):
        for record in self:
            remaining_lines = record.requisition_order_ids.filtered(lambda line: line.remaining_qty > 0)
            if record.purchase_order_ids and record.purchase_order_ids.filtered(lambda po: po.state == 'draft'):
                record.active_create_po = False
            elif not remaining_lines:
                record.active_create_po = False
            else:
                record.active_create_po = True
                

    def _get_purchase_order_ids(self):
        for record in self:
            purchase_ids = []
            for line in record.requisition_order_ids:
                if line.purchase_ids:
                    purchase_ids.extend(line.purchase_ids.ids)
                # purchase_order_line_ids = self.env['purchase.order.line'].sudo().search([('requisition_id', '=', record.id)])
                # if purchase_order_line_ids:
                #     for purchase_line in purchase_order_line_ids:
                #         if purchase_line.order_id.id not in purchase_ids:
                #             purchase_ids.append(purchase_line.order_id.id)
            if purchase_ids:
                purchase_ids = set(purchase_ids)
                record.purchase_order_ids = [(6, 0, purchase_ids)]
            else:
                record.purchase_order_ids = False

    def get_purchase_order(self):
        """Purchase order smart button view"""
        self.ensure_one()
        purchase_ids = []
        for line in self.requisition_order_ids:
            if line.purchase_ids:
                purchase_ids.extend(line.purchase_ids.ids)
        if purchase_ids:
            purchase_ids = list(set(purchase_ids))
        if not purchase_ids:
            raise ValidationError("No Purchase Order found.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Order',
            'view_mode': 'list,form',
            'res_model': 'purchase.order',
            'domain': [('id', 'in', purchase_ids)],
        }
    
    def _compute_purchase_count(self):
        """Function to compute the purchase count"""
        purchase_count = 0
        purchase_ids = []
        for line in self.requisition_order_ids:
            if line.purchase_ids:
                purchase_ids.extend(line.purchase_ids.ids)
        if purchase_ids:
            purchase_ids = list(set(purchase_ids))
            purchase_count = self.env['purchase.order'].search_count([
                ('id', 'in', purchase_ids)])
        self.purchase_count = purchase_count

    def button_create_purchase_order(self):
        """Create purchase order"""
        purchase_ids = []
        for record in self:
            order_line = []
            for requisition_order_id in record.requisition_order_ids.filtered(lambda line: line.remaining_qty > 0):
                line_name = False
                if requisition_order_id.product_id.name and requisition_order_id.description:
                    line_name = requisition_order_id.product_id.name + '\n' + requisition_order_id.description
                elif requisition_order_id.product_id.name:
                    line_name = requisition_order_id.product_id.name
                elif requisition_order_id.description:
                    line_name = requisition_order_id.description
                else:
                    line_name = requisition_order_id.product_id.product_id.name
                order_line.append((0, 0, {
                    'line_no': requisition_order_id.line_no,
                    'product_id': requisition_order_id.product_id.id,
                    'product_qty': requisition_order_id.remaining_qty,
                    'price_unit': requisition_order_id.estimate_price,
                    'analytic_distribution': requisition_order_id.analytic_distribution,
                    'remark': requisition_order_id.remark,
                    'product_uom_id': requisition_order_id.uom_id.id,
                    'requisition_id': requisition_order_id.requisition_product_id.id,
                    'requisition_line_id': requisition_order_id.id,
                    'name': line_name,
                }))

            purchase_id = self.env['purchase.order'].create({
                'partner_id': record.partner_id.id,
                'requisition_order': record.name,
                'requisition_order_ids' : [(4, record.id)],
                'source_document': record.internal_reference,
                'order_line': order_line
            })
            # menghubungkan setiap line purchase order dengan purchase order yang dibuat
            for line in record.requisition_order_ids:
                 line.purchase_ids = [(4, purchase_id.id)]
                 line._compute_ordered_remaining_qty()

            purchase_ids.append(purchase_id.id)
            record.write({'state': 'purchase_order_created'})
            # menghitung harga satuan, tanggal plan, dan nama barang
            for line_purchase in purchase_id.order_line:
                line_purchase._compute_price_unit_and_date_planned_and_name()
                
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Order',
            'view_mode': 'list,form',
            'res_model': 'purchase.order',
            'domain': [('id', 'in', purchase_ids)],
        }
    
    def write(self, vals):
        res = super(EmployeePurchaseRequisitionInherit, self).write(vals)
        if 'active' in vals:
            for record in self:
                if not vals['active']:
                    for line in record.requisition_order_ids:
                        line.active = False
                elif vals['active']:
                    for line in record.requisition_order_ids.search([('active', '=', False), ('requisition_product_id', '=', record.id)]):
                        line.active = True
        return res
        

class RequisitionOrderInherit(models.Model):
    _inherit = 'requisition.order'

    ordered_qty = fields.Integer('Ordered Qty')
    remaining_qty = fields.Integer('Remaining Qty')
    outstanding_qty = fields.Integer('Outstanding Qty')
    purchase_ids = fields.Many2many('purchase.order', string='Purchase Orders')
    purchase_request_type_id = fields.Many2one(comodel_name='purchase.request.type.master', string='Purchase Request Type', help='Type of Purchase Request', related='requisition_product_id.purchase_request_type_id')
    partner_id = fields.Many2one('res.partner', string='Vendor', help='Vendor for this purchase request line', related='requisition_product_id.partner_id')
    company_id = fields.Many2one('res.company', string='Company', related='requisition_product_id.company_id', store=True)
    department_id = fields.Many2one('hr.department', string='Division', related='requisition_product_id.department_id', store=True)
    active = fields.Boolean(string='Active', default=True)

    def action_deactivate_line(self):
        """Deactivate purchase requisition line"""
        for record in self:
            record.active = False

    def _compute_ordered_remaining_qty(self):
        for record in self:
            purchase_lines = self.env['purchase.order.line'].search([('requisition_line_id', '=', record.id)])
            submitted_lines = self.env['purchase.order.line'].search([('requisition_line_id', '=', record.id), ('state', '!=', 'draft')])
            ordered_qty = sum(purchase_lines.mapped('product_qty'))
            outstanding_qty = sum(submitted_lines.mapped('product_qty'))
            record.ordered_qty = ordered_qty
            record.outstanding_qty = outstanding_qty
            record.remaining_qty = record.quantity - ordered_qty


    def get_purchase_order(self):
        """Purchase order smart button view"""
        self.ensure_one()
        purchase_ids = self.requisition_order_ids.mapped('purchase_ids').ids
        if not purchase_ids:
            raise ValidationError("No Purchase Order found.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Order',
            'view_mode': 'list,form',
            'res_model': 'purchase.order',
            'domain': [('id', 'in', purchase_ids)],
        }
    
    def _compute_purchase_count(self):
        """Function to compute the purchase count"""
        purchase_ids = self.requisition_order_ids.mapped('purchase_ids').ids
        self.purchase_count = self.env['purchase.order'].search_count([
            ('id', 'in', purchase_ids)])

    def check_vendor_consistency(self):
        vendor_id = False
        for record in self:
            partner_id = record.partner_id.id if record.partner_id else False
            if not partner_id:
                raise ValidationError("Please set a vendor for the purchase request line.")
            if not vendor_id or vendor_id == partner_id:
                vendor_id = partner_id
            else:
                raise ValidationError("All selected purchase request lines must have the same vendor.")
        return vendor_id
    
    def check_currency_consistency(self):
        currency_id = False
        for record in self:
            curr_id = record.currency_id.id if record.currency_id else False
            if not curr_id:
                raise ValidationError("Please set a currency for the purchase request line.")
            if not currency_id or currency_id == curr_id:
                currency_id = curr_id
            else:
                raise ValidationError("All selected purchase request lines must have the same currency.")
        return currency_id
    
    def check_department_consistency(self):
        department_id = False
        for record in self:
            dept_id = record.department_id.id if record.department_id else False
            if not dept_id:
                raise ValidationError("Please set a division for the purchase request line.")
            if not department_id or department_id == dept_id:
                department_id = dept_id
            else:
                raise ValidationError("All selected purchase request lines must have the same division.")
        return department_id

    # def action_open_pr_create_po_wizard(self):
    #     # self.ensure_one()
    #     line_ids = []
    #     department_id = self.check_department_consistency()
    #     vendor_id = self.check_vendor_consistency()
    #     currency_id = self.check_currency_consistency()
    #     # line_ids = []
    #     for record in self:
    #         line_ids.append((0, 0, {
    #             'request_line_id': record.id,
    #             'analytic_distribution': record.analytic_distribution,
    #             'analytic_precision': record.analytic_precision,
    #             'currency_id': record.currency_id.id,
    #             'description': record.description,
    #             'display_name': record.display_name,
    #             'distribution_analytic_account_ids': record.distribution_analytic_account_ids,
    #             'estimate_price': record.estimate_price,
    #             'line_no': record.line_no,
    #             'partner_id': record.partner_id.id,
    #             'quantity': record.quantity,
    #             'product_id': record.product_id.id,
    #             'requisition_product_id': record.requisition_product_id.id,
    #             'requisition_type': record.requisition_type,
    #             'remaining_qty': record.remaining_qty,
    #             'department_id': department_id,
    #             'ordered_qty': record.ordered_qty,
    #             'state': record.state,
    #             'uom': record.uom,
    #             'uom_id': record.uom_id.id,
    #             'purchase_ids': record.purchase_ids.ids,
    #         }))
    #         # line_vals = {
    #         #     'request_line_id': record.id,
    #         #     'analytic_distribution': record.analytic_distribution,
    #         #     'analytic_precision': record.analytic_precision,
    #         #     'currency_id': record.currency_id.id,
    #         #     'description': record.description,
    #         #     'display_name': record.display_name,
    #         #     'distribution_analytic_account_ids': record.distribution_analytic_account_ids.ids,
    #         #     'estimate_price': record.estimate_price,
    #         #     'line_no': record.line_no,
    #         #     'partner_id': record.partner_id.id,
    #         #     'quantity': record.quantity,
    #         #     'product_id': record.product_id.id,
    #         #     'requisition_product_id': record.requisition_product_id.id,
    #         #     'requisition_type': record.requisition_type,
    #         #     'remaining_qty': record.remaining_qty,
    #         #     'department_id': department_id,
    #         #     'ordered_qty': record.ordered_qty,
    #         #     'state': record.state,
    #         #     'uom': record.uom,
    #         #     'uom_id': record.uom_id.id,
    #         #     'purchase_ids': record.purchase_ids.ids,
    #         # }
    #         # line_id = self.env['pr.line.po.wizard'].create(line_vals)
    #         # line_ids.append(line_id.id)
    #     wizard = self.env['pr.create.po.wizard'].create({
    #         'vendor_id': vendor_id,
    #         'currency_id': currency_id,
    #         'department_id': department_id,
    #         'line_ids': line_ids,
    #     })
    #     self.env.cr.commit()
    #     # context = {
    #     #     'default_vendor_id': vendor_id,
    #     #     'default_currency_id': currency_id,
    #     #     'default_department_id': department_id,
    #     #     'default_line_ids': line_ids,
    #     # }
    #     return {
    #         'name': 'Create Purchase Order from Purchase Request',
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'pr.create.po.wizard',
    #         'view_mode': 'form',
    #         'target': 'new',
    #         'res_id': wizard.id,
    #         # 'context': context,
    #     }
    
    def action_open_pr_create_po_wizard(self):
        line_ids = []
        department_id = self.check_department_consistency()
        vendor_id = self.check_vendor_consistency()
        currency_id = self.check_currency_consistency()
        
        for record in self:
            # Skip records that reference deleted related records
            if not record.exists():
                continue
                
            # Validate that required related records exist and are accessible
            required_fields = ['currency_id', 'partner_id', 'product_id', 'uom_id']
            skip_record = False
            
            for field in required_fields:
                field_value = record[field]
                if not field_value or not field_value.exists():
                    skip_record = True
                    _logger.warning(f"Skipping record {record.id}: {field} is missing or deleted")
                    break
                    
            if skip_record:
                continue
                
            # Safe access to related records with exists() check
            try:
                line_data = {
                    'request_line_id': record.id,
                    'analytic_distribution': record.analytic_distribution,
                    'analytic_precision': record.analytic_precision,
                    'currency_id': record.currency_id.id,
                    'description': record.description,
                    'display_name': record.display_name,
                    'estimate_price': record.estimate_price,
                    'line_no': record.line_no,
                    'partner_id': record.partner_id.id,
                    'quantity': record.quantity,
                    'product_id': record.product_id.id,
                    'requisition_type': record.requisition_type,
                    'remaining_qty': record.remaining_qty,
                    'department_id': department_id,
                    'ordered_qty': record.ordered_qty,
                    'state': record.state,
                    'uom': record.uom,
                    'uom_id': record.uom_id.id,
                }
                
                # Add optional fields only if they exist
                if record.distribution_analytic_account_ids and record.distribution_analytic_account_ids.exists():
                    line_data['distribution_analytic_account_ids'] = record.distribution_analytic_account_ids.ids
                
                if record.requisition_product_id and record.requisition_product_id.exists():
                    line_data['requisition_product_id'] = record.requisition_product_id.id
                
                if record.purchase_ids and record.purchase_ids.exists():
                    line_data['purchase_ids'] = record.purchase_ids.ids
                else:
                    line_data['purchase_ids'] = []
                    
                line_ids.append((0, 0, line_data))
                
            except Exception as e:
                _logger.warning(f"Error processing record {record.id}: {str(e)}")
                raise UserError(_(f"Error processing record {record.id}: {str(e)}"))
                # continue
        
        if not line_ids:
            raise UserError(_("No valid records found to create purchase order."))
        
        wizard = self.env['pr.create.po.wizard'].create({
            'vendor_id': vendor_id,
            'currency_id': currency_id,
            'department_id': department_id,
            'line_ids': line_ids,
        })
        
        return {
            'name': 'Create Purchase Order from Purchase Request',
            'type': 'ir.actions.act_window',
            'res_model': 'pr.create.po.wizard',
            'view_mode': 'form',
            'target': 'new',
            'res_id': wizard.id,
        }
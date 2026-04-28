from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class PrCreatePoWizard(models.TransientModel):
    _name = 'pr.create.po.wizard'
    _description = 'Purchase Request Create PO Wizard'

    vendor_id = fields.Many2one('res.partner', string='Vendor', required=True)
    department_id = fields.Many2one('hr.department', string='Division')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.company.currency_id)
    requisition_ids = fields.Many2many('employee.purchase.requisition', string='Purchase Request', compute='_compute_requisition')
    requisition_line_ids = fields.Many2many('requisition.order', string='Purchase Request Lines', compute='_compute_requisition_lines')
    line_ids = fields.One2many('pr.line.po.wizard', 'parent_id', string='Purchase Request Lines')

    def _compute_requisition(self):
        for record in self:
            requisition_ids = []
            for line in record.line_ids:
                if (line.requisition_product_id and 
                    line.requisition_product_id.exists() and 
                    line.requisition_product_id.id not in requisition_ids):
                    requisition_ids.append(line.requisition_product_id.id)
            
            if requisition_ids:
                record.requisition_ids = [(6, 0, requisition_ids)]
            else:
                record.requisition_ids = False

    def _compute_requisition_lines(self):
        for record in self:
            requisition_line_ids = []
            for line in record.line_ids:
                if (line.request_line_id and 
                    line.request_line_id.exists() and 
                    line.request_line_id.id not in requisition_line_ids):
                    requisition_line_ids.append(line.request_line_id.id)
            
            if requisition_line_ids:
                record.requisition_line_ids = [(6, 0, requisition_line_ids)]
            else:
                record.requisition_line_ids = False

    def action_create_po(self):
        self.ensure_one()
        
        if not self.line_ids:
            raise ValidationError("No purchase request lines found.")
            
        # Filter valid lines
        valid_lines = []
        for line in self.line_ids:
            if not line.request_line_id or not line.request_line_id.exists():
                _logger.warning(f"Skipping line {line.id}: related request line not found")
                continue
            if not line.product_id or not line.product_id.exists():
                _logger.warning(f"Skipping line {line.id}: product not found")
                continue
            valid_lines.append(line)
            
        if not valid_lines:
            raise ValidationError("No valid purchase request lines found.")

        order_lines = []
        for line in valid_lines:
            if line.to_order_qty <= 0:
                raise ValidationError(f"Line {line.product_id.display_name} has an invalid to order quantity.")
            
            if line.to_order_qty > line.remaining_qty:
                raise ValidationError(f"Line {line.product_id.display_name} has a to order quantity ({line.to_order_qty}) greater than the remaining quantity ({line.remaining_qty}).")
            
            if line.remaining_qty <= 0:
                raise ValidationError(f"Line {line.product_id.display_name} has no remaining quantity to order.")
            
            # Create purchase order line
            line_name = False
            if line.request_line_id.product_id.name and line.request_line_id.description:
                line_name = line.request_line_id.product_id.name + '\n' + line.request_line_id.description
            elif line.request_line_id.product_id.name:
                line_name = line.request_line_id.product_id.name
            elif line.request_line_id.description:
                line_name = line.request_line_id.description
            else:
                line_name = line.product_id.product_id.name
            order_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line_name,
                'product_qty': line.to_order_qty,
                'product_uom_id': line.uom_id.id,
                'price_unit': line.estimate_price,
                'requisition_id': line.requisition_product_id.id if line.requisition_product_id and line.requisition_product_id.exists() else False,
                'requisition_line_id': line.request_line_id.id,
                'analytic_distribution': line.analytic_distribution,
            }))

        # Create purchase order
        purchase_vals = {
            'partner_id': self.vendor_id.id,
            'company_id': self.company_id.id,
            'department_id': self.department_id.id if self.department_id else False,
            'currency_id': self.currency_id.id,
            'order_line': order_lines,
        }
        
        if self.department_id and self.department_id.exists():
            purchase_vals['department_id'] = self.department_id.id
            
        if self.requisition_line_ids:
            purchase_vals['requisition_order_ids'] = [(6, 0, self.requisition_ids.ids)]
        
        purchase_id = self.env['purchase.order'].create(purchase_vals)
        
        # Update request lines
        for line in valid_lines:
            if line.to_order_qty > 0:
                line.request_line_id.purchase_ids = [(4, purchase_id.id)]
                line.request_line_id._compute_ordered_remaining_qty()
                
                # Update requisition product state if applicable
                if (line.requisition_product_id and 
                    line.requisition_product_id.exists()):
                    line.requisition_product_id.state = 'purchase_order_created'

        for line_purchase in purchase_id.order_line:
            line_purchase._compute_price_unit_and_date_planned_and_name()

        return {
            'name': 'Purchase Order',
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': purchase_id.id,
        }


class PrLinePoWizard(models.TransientModel):
    _name = 'pr.line.po.wizard'
    _description = 'Purchase Request Line for PO Wizard'

    parent_id = fields.Many2one('pr.create.po.wizard', string='Parent Wizard')
    request_line_id = fields.Many2one('requisition.order', string='Request Line')
    to_order_qty = fields.Float('To Order Quantity', default=0.0)
    
    # Copy relevant fields from requisition.order
    company_id = fields.Many2one('res.company', string='Company')
    analytic_distribution = fields.Json('Analytic Distribution')
    analytic_precision = fields.Integer('Analytic Precision')
    currency_id = fields.Many2one('res.currency', string='Currency')
    description = fields.Text('Description')
    display_name = fields.Char('Display Name')
    distribution_analytic_account_ids = fields.Many2many('account.analytic.account', string='Analytic Accounts')
    estimate_price = fields.Float('Estimate Price')
    line_no = fields.Char('Line No')
    partner_id = fields.Many2one('res.partner', string='Partner')
    quantity = fields.Float('Quantity')
    product_id = fields.Many2one('product.product', string='Product')
    requisition_product_id = fields.Many2one('employee.purchase.requisition', string='Requisition Product')
    requisition_type = fields.Selection(string='Requisition Type', selection=[
        ('purchase_order', 'Purchase Order'),
        ('internal_transfer', 'Internal Transfer'), ],
                                        help='Type of requisition',
                                        required=True, default='purchase_order')
    remaining_qty = fields.Float('Remaining Quantity')
    department_id = fields.Many2one('hr.department', string='Department')
    ordered_qty = fields.Float('Ordered Quantity')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting_approval', 'Waiting Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('purchase_order_created', 'Purchase Order Created'),
        ('cancel', 'Cancelled')], string='State')
    uom = fields.Char('UOM')
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    purchase_ids = fields.Many2many('purchase.order', string='Purchase Orders')
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountAsset(models.Model):
    _inherit = 'account.asset'

    partner_id = fields.Many2one(
        'res.partner',
        string="Partner Link",
        compute="_compute_partner_id"
    )

    @api.depends('original_move_line_ids.move_id.partner_id', 'vehicle_id.driver_id')
    def _compute_partner_id(self):
        for rec in self:
            partner = self.env['res.partner']
            if rec.original_move_line_ids:
                partners = rec.original_move_line_ids.mapped('move_id.partner_id')
                if partners:
                    partner = partners[0]
            if not partner and rec.vehicle_id and rec.vehicle_id.driver_id:
                partner = rec.vehicle_id.driver_id
            rec.partner_id = partner

    # Relation to payment & purchase order
    incoming_payment_ids = fields.One2many(
        'account.payment', 
        'asset_id', 
        string="Incoming Payments"
    )
    purchase_order_ids = fields.One2many(
        'purchase.order', 
        'asset_id', 
        string="Purchase Orders"
    )

    # Fields on Other Info tab
    incoming_payment_ref = fields.Many2one(
        'account.payment',
        string="Incoming Payment Reference",
        compute="_compute_incoming_payment_info",
        store=True,
        tracking=True
    )
    incoming_payment_status = fields.Selection([
        ('draft', 'Draft'),
        ('in_process', 'In Process'),
        ('paid', 'Paid'),
        ('canceled', 'Canceled'),
        ('rejected', 'Rejected'),
    ],
        string="Incoming Payment Status",
        compute="_compute_incoming_payment_info",
        store=True,
        tracking=True
    )
    purchase_order_ref = fields.Many2one(
        'purchase.order',
        string="Purchase Order Reference",
        compute="_compute_purchase_order_info",
        store=True,
        tracking=True
    )
    purchase_order_status = fields.Selection([
        ('draft', 'RFQ'),
        ('waiting_approval', 'Waiting Approval'),
        ('sent', 'RFQ Sent'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
        ('rejected', 'Rejected'),
    ],
        string="Purchase Order Status",
        compute="_compute_purchase_order_info",
        store=True,
        tracking=True
    )

    @api.depends('incoming_payment_ids.name', 'incoming_payment_ids.state')
    def _compute_incoming_payment_info(self):
        for rec in self:
            # Get the latest payment associated with the asset
            payment = rec.incoming_payment_ids.sorted(key='id', reverse=True)[:1]
            if payment:
                rec.incoming_payment_ref = payment.id
                rec.incoming_payment_status = payment.state
            else:
                rec.incoming_payment_ref = False
                rec.incoming_payment_status = False

    @api.depends('purchase_order_ids.name', 'purchase_order_ids.state')
    def _compute_purchase_order_info(self):
        for rec in self:
            # Get the latest purchase order associated with the asset
            po = rec.purchase_order_ids.sorted(key='id', reverse=True)[:1]
            if po:
                rec.purchase_order_ref = po.id
                rec.purchase_order_status = po.state
            else:
                rec.purchase_order_ref = False
                rec.purchase_order_status = False

    def action_create_incoming_payment(self):
        self.ensure_one()
        if self.incoming_payment_ref:
            raise UserError(_("Incoming Payment sudah dibuat untuk aset ini."))
        
        # Search for default income account and product
        account = self.env['account.account'].search([('code', '=', '41000010')], limit=1)
        if not account:
            account = self.env['account.account'].search([('account_type', '=', 'income')], limit=1)
            
        product = self.env['product.product'].search([('name', 'ilike', 'Pendapatan')], limit=1)
        
        # Prepare invoice lines
        line_vals = {
            'name': f"Leaseback - {self.name}",
            'quantity': 1,
            'price_unit': self.original_value or 0.0,
        }
        if product:
            line_vals['product_id'] = product.id
        if account:
            line_vals['account_id'] = account.id
            
        # Create draft invoice in database
        inv_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id if self.partner_id else False,
            'asset_id': self.id,
            'invoice_line_ids': [(0, 0, line_vals)]
        }
        self.env['account.move'].create(inv_vals)

        # Create draft payment immediately in database
        payment_vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_id.id if self.partner_id else False,
            'asset_id': self.id,
            'amount': self.original_value or 0.0,
        }
        payment = self.env['account.payment'].create(payment_vals)
        res_id = payment.id

        # Redirect to the payment form view
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_payments")
        action.update({
            'views': [(self.env.ref('account.view_account_payment_form').id, 'form')],
            'res_id': res_id,
            'context': {
                'default_payment_type': 'inbound',
                'default_partner_type': 'customer',
                'default_partner_id': self.partner_id.id if self.partner_id else False,
                'default_asset_id': self.id,
                'default_amount': self.original_value or 0.0,
            }
        })
        return action

    def action_create_purchase_order(self):
        self.ensure_one()
        if self.purchase_order_ref:
            raise UserError(_("Purchase Order sudah dibuat untuk aset ini."))
            
        res_id = False
        
        # Search for default PO Type and Division to pre-fill
        po_type = self.env['purchase.order.type.master'].search([('state', '=', 'active')], limit=1) or self.env['purchase.order.type.master'].search([], limit=1)
        department = self.env['hr.department'].search([], limit=1)

        # Create PO and confirm it directly only if partner is defined
        if self.partner_id:
            po = self.env['purchase.order'].create({
                'partner_id': self.partner_id.id,
                'origin': self.name,
                'partner_ref': self.name,
                'asset_id': self.id,
                'purchase_order_type_master_id': po_type.id if po_type else False,
                'department_id': department.id if department else False,
            })
            res_id = po.id

            # Find a product to add to the PO line
            product = False
            if self.original_move_line_ids:
                for line in self.original_move_line_ids:
                    if line.product_id:
                        product = line.product_id
                        break
            if not product:
                product = self.env['product.product'].search([('type', 'in', ('consu', 'product'))], limit=1)
            if not product:
                product = self.env['product.product'].search([], limit=1)

            # Create PO Line
            po_line_vals = {
                'order_id': po.id,
                'name': self.name,
                'product_qty': 1.0,
                'price_unit': self.original_value or 0.0,
            }
            if product:
                po_line_vals['product_id'] = product.id
                po_line_vals['product_uom_id'] = product.uom_id.id if product.uom_id else False
                
            if not po_line_vals.get('product_uom_id'):
                uom = self.env['uom.uom'].search([], limit=1)
                po_line_vals['product_uom_id'] = uom.id if uom else False

            self.env['purchase.order.line'].create(po_line_vals)

            # Directly confirm the PO (bypass approval matrix and make it active)
            try:
                po.button_approve()
            except Exception as e:
                pass

        # Redirect to the purchase.order form view
        action = self.env["ir.actions.actions"]._for_xml_id("purchase.purchase_form_action")
        action.update({
            'views': [(self.env.ref('purchase.purchase_order_form').id, 'form')],
            'res_id': res_id,
            'context': {
                'default_partner_id': self.partner_id.id if self.partner_id else False,
                'default_origin': self.name,
                'default_partner_ref': self.name,
                'default_asset_id': self.id,
                'default_purchase_order_type_master_id': po_type.id if po_type else False,
                'default_department_id': department.id if department else False,
            }
        })
        return action

    def _get_residual_value_at_date(self, date):
        self.ensure_one()
        current_and_previous_depreciation = self.depreciation_move_ids.filtered(
            lambda mv:
            mv.asset_depreciation_beginning_date
            and mv.asset_depreciation_beginning_date < date
            and not mv.reversed_entry_id
        ).sorted('asset_depreciation_beginning_date', reverse=True)
        if not current_and_previous_depreciation:
            return 0

        if len(current_and_previous_depreciation) > 1:
            previous_value_residual = current_and_previous_depreciation[1].asset_remaining_value
        else:
            previous_value_residual = self.original_value - self.salvage_value - self.already_depreciated_amount_import

        cur_depr_end_date = self._get_end_period_date(date)
        current_depreciation = current_and_previous_depreciation[0]
        cur_depr_beg_date = current_depreciation.asset_depreciation_beginning_date

        rate = self._get_delta_days(cur_depr_beg_date, date) / self._get_delta_days(cur_depr_beg_date, cur_depr_end_date)
        lost_value_at_date = (previous_value_residual - current_depreciation.asset_remaining_value) * rate
        residual_value_at_date = self.currency_id.round(previous_value_residual - lost_value_at_date)
        if self.currency_id.compare_amounts(self.original_value, 0) > 0:
            return max(residual_value_at_date, 0)
        else:
            return min(residual_value_at_date, 0)

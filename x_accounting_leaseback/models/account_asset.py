from odoo import models, fields, api, _

class AccountAsset(models.Model):
    _inherit = 'account.asset'

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
        ('draft', 'Draft PO'),
        ('sent', 'RFQ Sent'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('cancel', 'Cancelled')
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
        # Redirect to account.payment form view
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_payments")
        action.update({
            'views': [(self.env.ref('account.view_account_payment_form').id, 'form')],
            'res_id': False,
            'context': {
                'default_payment_type': 'inbound',
                'default_partner_type': 'customer',
                'default_partner_id': self.partner_id.id if self.partner_id else False,
                'default_asset_id': self.id,
            }
        })
        return action

    def action_create_purchase_order(self):
        self.ensure_one()
        # Redirect to purchase.order form view
        action = self.env["ir.actions.actions"]._for_xml_id("purchase.purchase_form_action")
        action.update({
            'views': [(self.env.ref('purchase.purchase_order_form').id, 'form')],
            'res_id': False,
            'context': {
                'default_partner_id': self.partner_id.id if self.partner_id else False,
                'default_origin': self.name,
                'default_asset_id': self.id,
            }
        })
        return action

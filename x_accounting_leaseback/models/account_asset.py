from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountAsset(models.Model):
    _inherit = 'account.asset'

    partner_id = fields.Many2one(
        'res.partner',
        string="Partner Link",
        compute="_compute_partner_id",
    )

    @api.depends('original_move_line_ids.move_id.partner_id')
    def _compute_partner_id(self):
        for rec in self:
            partner = self.env['res.partner']
            if rec.original_move_line_ids:
                partners = rec.original_move_line_ids.mapped('move_id.partner_id')
                if partners:
                    partner = partners[0]
            rec.partner_id = partner

    incoming_payment_ids = fields.One2many(
        'account.payment',
        'asset_id',
        string="Incoming Payments",
    )
    purchase_order_ids = fields.One2many(
        'purchase.order',
        'asset_id',
        string="Purchase Orders",
    )

    incoming_payment_ref = fields.Many2one(
        'account.payment',
        string="Incoming Payment Reference",
        compute="_compute_incoming_payment_info",
        store=True,
        tracking=True,
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
        tracking=True,
    )
    purchase_order_ref = fields.Many2one(
        'purchase.order',
        string="Purchase Order Reference",
        compute="_compute_purchase_order_info",
        store=True,
        tracking=True,
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
        tracking=True,
    )

    @api.depends('incoming_payment_ids.name', 'incoming_payment_ids.state')
    def _compute_incoming_payment_info(self):
        for rec in self:
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

        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_payments")
        action.update({
            'views': [(self.env.ref('account.view_account_payment_form').id, 'form')],
            'view_mode': 'form',
            'target': 'current',
            'context': {
                **self.env.context,
                'default_payment_type': 'inbound',
                'default_partner_type': 'customer',
                'default_partner_id': self.partner_id.id if self.partner_id else False,
                'default_asset_id': self.id,
            },
        })
        return action

    def _get_purchase_order_redirect_context(self):
        self.ensure_one()
        context = {
            **self.env.context,
            'default_origin': self.name,
            'default_partner_ref': self.name,
            'default_asset_id': self.id,
        }
        if self.partner_id:
            context['default_partner_id'] = self.partner_id.id

        po_model = self.env['purchase.order']
        if 'purchase_order_type_master_id' in po_model._fields:
            po_type = (
                self.env['purchase.order.type.master'].search([('state', '=', 'active')], limit=1)
                or self.env['purchase.order.type.master'].search([], limit=1)
            )
            if po_type:
                context['default_purchase_order_type_master_id'] = po_type.id
        if 'department_id' in po_model._fields:
            department = self.env['hr.department'].search([], limit=1)
            if department:
                context['default_department_id'] = department.id
        return context

    def action_create_purchase_order(self):
        self.ensure_one()
        if self.purchase_order_ref:
            raise UserError(_("Purchase Order sudah dibuat untuk aset ini."))

        action = self.env["ir.actions.actions"]._for_xml_id("purchase.purchase_form_action")
        action.update({
            'views': [(self.env.ref('purchase.purchase_order_form').id, 'form')],
            'view_mode': 'form',
            'target': 'current',
            'context': self._get_purchase_order_redirect_context(),
        })
        return action

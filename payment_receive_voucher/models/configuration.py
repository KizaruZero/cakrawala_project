from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class VoucherConfiguration(models.Model):
    _name = 'prv.voucher.config'
    _description = 'Voucher Approval Configuration'
    _check_company_auto = True

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    show_pay_button = fields.Boolean(
        string='Show Pay Button on Voucher',
        default=False,
        help='When enabled, approved vouchers show a Pay button that opens the standard Odoo payment registration wizard.',
    )
    require_same_partner = fields.Boolean(
        string='Require Same Vendor / Customer',
        default=True,
        help='When enabled, all source documents in one voucher must have the same vendor or customer. Company and currency must always match.',
    )
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    voucher_type = fields.Selection([('payment', 'Payment Voucher'), ('receive', 'Receive Voucher')], required=True)
    payment_voucher_type_id = fields.Many2one(
        'prv.voucher.payment.type', string='Payment Voucher Type', check_company=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
        help='Leave empty for a general fallback configuration. A specific type configuration takes precedence.',
    )
    approval_scope = fields.Char(compute='_compute_approval_scope', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    layer_ids = fields.One2many('prv.voucher.config.layer', 'config_id', copy=True)
    _company_type_scope_unique = models.Constraint(
        'UNIQUE(company_id, voucher_type, approval_scope)',
        'Only one approval configuration per company, voucher type and Payment Voucher Type is allowed, including archived configurations.',
    )

    @api.depends('voucher_type', 'payment_voucher_type_id')
    def _compute_approval_scope(self):
        for config in self:
            config.approval_scope = (
                str(config.payment_voucher_type_id.id)
                if config.voucher_type == 'payment' and config.payment_voucher_type_id
                else '*'
            )

    @api.constrains('company_id', 'voucher_type', 'payment_voucher_type_id')
    def _check_payment_voucher_type(self):
        for config in self:
            if config.voucher_type == 'receive' and config.payment_voucher_type_id:
                raise ValidationError(_('Payment Voucher Type can only be set on Payment Voucher configurations.'))
            if config.payment_voucher_type_id and config.payment_voucher_type_id.company_id != config.company_id:
                raise ValidationError(_('Payment Voucher Type must belong to the same company as the configuration.'))

    @api.model
    def get_for_voucher(self, company, voucher_type, payment_voucher_type=None):
        base = [('company_id', '=', company.id), ('voucher_type', '=', voucher_type), ('active', '=', True)]
        if voucher_type == 'payment' and payment_voucher_type:
            specific = self.sudo().search(base + [('payment_voucher_type_id', '=', payment_voucher_type.id)], limit=1)
            if specific:
                return specific
        return self.sudo().search(base + [('payment_voucher_type_id', '=', False)], limit=1)


class VoucherConfigurationLayer(models.Model):
    _name = 'prv.voucher.config.layer'
    _description = 'Voucher Approval Layer Configuration'
    _order = 'sequence, id'
    _check_company_auto = True

    config_id = fields.Many2one('prv.voucher.config', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='config_id.company_id', store=True)
    currency_id = fields.Many2one(related='config_id.currency_id')
    sequence = fields.Integer(string='Layer', required=True, default=1)
    min_amount = fields.Monetary(string='Threshold (inclusive)', default=0, required=True)
    approver_id = fields.Many2one('res.users', required=True, ondelete='restrict', domain=[('share', '=', False)])
    delegate_id = fields.Many2one('res.users', ondelete='restrict', domain=[('share', '=', False)])
    valid_from = fields.Date(string='Delegation Valid From')
    valid_until = fields.Date(string='Delegation Valid Until')
    _sequence_unique = models.Constraint('UNIQUE(config_id, sequence)', 'Layer numbers must be unique within a configuration.')

    @api.constrains('sequence', 'min_amount', 'approver_id', 'delegate_id', 'valid_from', 'valid_until', 'config_id')
    def _check_layer(self):
        for layer in self:
            if layer.sequence < 1 or layer.min_amount < 0:
                raise ValidationError(_('Layer must be positive and threshold must not be negative.'))
            if layer.delegate_id and (not layer.valid_from or not layer.valid_until or layer.valid_from > layer.valid_until):
                raise ValidationError(_('Delegation requires a valid inclusive date range.'))
            for user in layer.approver_id | layer.delegate_id:
                if (not user.active or user.share or layer.company_id not in user.company_ids
                        or not user.has_group('payment_receive_voucher.group_voucher_approver')):
                    raise ValidationError(_('Approvers and delegates must be active Voucher Approvers with access to the company.'))

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
    currency_id = fields.Many2one(related='company_id.currency_id')
    layer_ids = fields.One2many('prv.voucher.config.layer', 'config_id', copy=True)
    _company_type_unique = models.Constraint('UNIQUE(company_id, voucher_type)',
                                             'Only one configuration per company and voucher type is allowed, including archived configurations.')


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

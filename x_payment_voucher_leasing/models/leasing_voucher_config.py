# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class LeasingVoucherConfig(models.Model):
    _name = 'leasing.voucher.config'
    _description = 'Leasing Voucher Approval Configuration'
    _check_company_auto = True

    name = fields.Char(required=True, default='Leasing Payment Voucher Policy')
    active = fields.Boolean(default=True)
    require_same_partner = fields.Boolean(
        string='Require Same Vendor',
        default=True,
        help='When enabled, all leasing lines in one voucher must belong to the same leasing vendor.',
    )
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    layer_ids = fields.One2many('leasing.voucher.config.layer', 'config_id', string='Approval Layers', copy=True)

    _company_unique = models.Constraint(
        'UNIQUE(company_id)',
        'Hanya boleh ada satu konfigurasi approval per perusahaan.'
    )


class LeasingVoucherConfigLayer(models.Model):
    _name = 'leasing.voucher.config.layer'
    _description = 'Leasing Voucher Approval Layer'
    _order = 'sequence, id'
    _check_company_auto = True

    config_id = fields.Many2one('leasing.voucher.config', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='config_id.company_id', store=True)
    currency_id = fields.Many2one(related='config_id.currency_id')
    sequence = fields.Integer(string='Layer', required=True, default=1)
    min_amount = fields.Monetary(string='Threshold Min Amount (Inclusive)', default=0, required=True)
    approver_id = fields.Many2one('res.users', string='Approver', required=True, ondelete='restrict', domain=[('share', '=', False)])
    delegate_id = fields.Many2one('res.users', string='Delegate', ondelete='restrict', domain=[('share', '=', False)])
    valid_from = fields.Date(string='Delegation Valid From')
    valid_until = fields.Date(string='Delegation Valid Until')

    _sequence_unique = models.Constraint(
        'UNIQUE(config_id, sequence)',
        'Nomor urut layer harus unik dalam satu konfigurasi.'
    )

    @api.constrains('sequence', 'min_amount', 'approver_id', 'delegate_id', 'valid_from', 'valid_until')
    def _check_layer(self):
        for layer in self:
            if layer.sequence < 1 or layer.min_amount < 0:
                raise ValidationError(_('Nomor layer harus lebih besar dari 0 dan nilai threshold tidak boleh negatif.'))
            if layer.delegate_id and (not layer.valid_from or not layer.valid_until or layer.valid_from > layer.valid_until):
                raise ValidationError(_('Delegasi membutuhkan rentang tanggal Valid From dan Valid Until yang valid.'))
            for user in layer.approver_id | layer.delegate_id:
                is_approver = user.has_group('x_payment_voucher_leasing.group_leasing_voucher_approver') or user.has_group('base.group_system')
                if not user.active or user.share or layer.company_id not in user.company_ids or not is_approver:
                    raise ValidationError(_(
                        'User %s harus merupakan user aktif dengan hak akses Approver Voucher Leasing dan memiliki akses ke perusahaan terkait.',
                        user.name
                    ))

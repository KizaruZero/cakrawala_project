# -*- coding: utf-8 -*-
from odoo import fields, models


class LeasingPaymentVoucherHistory(models.Model):
    _name = 'leasing.payment.voucher.history'
    _description = 'Leasing Voucher Audit History'
    _order = 'id desc'

    voucher_id = fields.Many2one('leasing.payment.voucher', required=True, ondelete='cascade', index=True)
    date = fields.Datetime(string='Date', default=fields.Datetime.now, required=True)
    sequence = fields.Integer(string='Layer')
    approver_id = fields.Many2one('res.users', string='Target Approver')
    actor_id = fields.Many2one('res.users', string='Executed By', required=True)
    action = fields.Char(string='Action', required=True)
    delegated = fields.Boolean(string='Delegated', default=False)
    remarks = fields.Text(string='Remarks')

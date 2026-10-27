# -*- coding: utf-8 -*-
from odoo import fields, models


class LeasingPaymentVoucherStep(models.Model):
    _name = 'leasing.payment.voucher.step'
    _description = 'Leasing Voucher Approval Step'
    _order = 'sequence, id'

    voucher_id = fields.Many2one('leasing.payment.voucher', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='Layer', required=True)
    approver_id = fields.Many2one('res.users', string='Approver', required=True)
    delegate_id = fields.Many2one('res.users', string='Delegate')
    valid_from = fields.Date(string='Valid From')
    valid_until = fields.Date(string='Valid Until')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending', required=True)
    actor_id = fields.Many2one('res.users', string='Acted By')
    acted_at = fields.Datetime(string='Acted At')
    remarks = fields.Text(string='Remarks')

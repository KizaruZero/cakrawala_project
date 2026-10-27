# -*- coding: utf-8 -*-
from odoo import fields, models


class LeasingVoucherDecision(models.TransientModel):
    _name = 'leasing.voucher.decision'
    _description = 'Leasing Voucher Approval Decision'

    voucher_id = fields.Many2one('leasing.payment.voucher', required=True, readonly=True)
    decision = fields.Selection([
        ('approve', 'Approve'),
        ('reject', 'Reject')
    ], required=True, readonly=True)
    remarks = fields.Text(string='Catatan / Alasan')

    def action_confirm(self):
        self.ensure_one()
        self.voucher_id._decision(self.decision, self.remarks or '')
        return {'type': 'ir.actions.act_window_close'}

from odoo import fields, models


class VoucherDecision(models.TransientModel):
    _name = 'prv.voucher.decision'
    _description = 'Voucher Approval Decision'

    voucher_id = fields.Many2one('prv.voucher', required=True, readonly=True)
    decision = fields.Selection([('approve', 'Approve'), ('reject', 'Reject')], required=True, readonly=True)
    remarks = fields.Text()

    def action_confirm(self):
        self.ensure_one()
        self.voucher_id._decision(self.decision, self.remarks or '')
        return {'type': 'ir.actions.act_window_close'}

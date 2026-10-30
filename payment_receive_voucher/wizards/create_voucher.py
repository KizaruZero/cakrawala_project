from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class CreatePaymentVoucher(models.TransientModel):
    _name = 'prv.voucher.create'
    _description = 'Create Payment Voucher'

    move_ids = fields.Many2many('account.move', string='Vendor Bills', readonly=True)
    company_id = fields.Many2one('res.company', compute='_compute_company', readonly=True)
    payment_voucher_type_id = fields.Many2one(
        'prv.voucher.payment.type', string='Payment Voucher Type', required=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )

    @api.depends('move_ids.company_id')
    def _compute_company(self):
        for wizard in self:
            wizard.company_id = wizard.move_ids[:1].company_id

    def action_confirm(self):
        self.ensure_one()
        if not self.env.user.has_group('payment_receive_voucher.group_voucher_user'):
            raise AccessError(_('Voucher User access is required.'))
        moves = self.move_ids.exists()
        moves.check_access('read')
        moves._prv_validate_selection('payment', payment_voucher_type=self.payment_voucher_type_id)
        if not self.payment_voucher_type_id or self.payment_voucher_type_id.company_id != moves.company_id:
            raise UserError(_('Choose an active Payment Voucher Type for the same company as the selected bills.'))
        voucher = self.env['prv.voucher'].create({
            'voucher_type': 'payment',
            'payment_voucher_type_id': self.payment_voucher_type_id.id,
            'move_ids': [(6, 0, moves.ids)],
        })
        return {'type': 'ir.actions.act_window', 'res_model': 'prv.voucher',
                'view_mode': 'form', 'res_id': voucher.id, 'target': 'current'}

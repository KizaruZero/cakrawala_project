# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class LeasingPaymentVoucherLine(models.Model):
    _name = 'leasing.payment.voucher.line'
    _description = 'Leasing Payment Voucher Selected Line'
    _order = 'loan_id, installment_number, id'

    voucher_id = fields.Many2one('leasing.payment.voucher', required=True, ondelete='cascade', index=True)
    loan_line_id = fields.Many2one('account.loan.line', string='Installment Line', required=True, ondelete='restrict', index=True)
    loan_id = fields.Many2one('account.loan', string='Leasing Agreement', required=True)
    vendor_id = fields.Many2one(
        'res.partner', string='Vendor / Leasing Partner',
        help='Snapshot penerima pembayaran. Voucher baru mengikuti Leasing Partner PO; data voucher lama dipertahankan.',
    )
    po_number = fields.Char(string='PO Number')
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle')
    license_plate = fields.Char(string='Plate Number')
    installment_number = fields.Integer(string='Angs. ke')
    date = fields.Date(string='Tanggal')
    
    currency_id = fields.Many2one(related='voucher_id.currency_id')
    company_id = fields.Many2one(related='voucher_id.company_id', store=True)

    principal = fields.Monetary(string='Pokok', currency_field='currency_id')
    interest = fields.Monetary(string='Bunga', currency_field='currency_id')
    total = fields.Monetary(string='Total', currency_field='currency_id')
    remaining_principal = fields.Monetary(string='Saldo Pokok', currency_field='currency_id')
    remaining_interest = fields.Monetary(string='Saldo Bunga', currency_field='currency_id')

    payment_move_id = fields.Many2one('account.move', string='Payment Journal Entry', readonly=True)

    @api.model_create_multi
    def create(self, values_list):
        default_voucher = (self.default_get(['voucher_id']).get('voucher_id')
                           if any('voucher_id' not in values for values in values_list) else False)
        vouchers = self.env['leasing.payment.voucher'].browse([
            values.get('voucher_id', default_voucher) for values in values_list
            if values.get('voucher_id', default_voucher)
        ])
        if vouchers.filtered(lambda voucher: voucher.state != 'draft'):
            raise UserError(_('Detail voucher yang sudah diajukan tidak dapat ditambah.'))
        return super().create(values_list)

    def write(self, values):
        if {'vendor_id', 'voucher_id', 'loan_id', 'loan_line_id'}.intersection(values):
            vouchers = self.voucher_id
            if values.get('voucher_id'):
                vouchers |= self.env['leasing.payment.voucher'].browse(values['voucher_id'])
            if vouchers.filtered(lambda voucher: voucher.state != 'draft'):
                raise UserError(_('Penerima/sumber detail voucher yang sudah diajukan tidak dapat diubah. Batalkan dan buat ulang voucher.'))
        return super().write(values)

    def unlink(self):
        if self.voucher_id.filtered(lambda voucher: voucher.state != 'draft'):
            raise UserError(_('Detail voucher yang sudah diajukan tidak dapat dihapus.'))
        return super().unlink()

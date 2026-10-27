# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LeasingPaymentVoucherLine(models.Model):
    _name = 'leasing.payment.voucher.line'
    _description = 'Leasing Payment Voucher Selected Line'
    _order = 'loan_id, installment_number, id'

    voucher_id = fields.Many2one('leasing.payment.voucher', required=True, ondelete='cascade', index=True)
    loan_line_id = fields.Many2one('account.loan.line', string='Installment Line', required=True, ondelete='restrict', index=True)
    loan_id = fields.Many2one('account.loan', string='Leasing Agreement', required=True)
    vendor_id = fields.Many2one('res.partner', string='Vendor')
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

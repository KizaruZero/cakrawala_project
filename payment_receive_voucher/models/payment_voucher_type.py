from odoo import fields, models, _


class PaymentVoucherType(models.Model):
    _name = 'prv.voucher.payment.type'
    _description = 'Payment Voucher Type'
    _order = 'company_id, name'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    _name_company_unique = models.Constraint('UNIQUE(company_id, name)', 'Payment Voucher Type names must be unique per company.')

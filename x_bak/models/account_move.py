from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    bak_id = fields.Many2one(
        'bak',
        string='BAK Reference',
        readonly=True,
        copy=False,
        help='Referensi ke Berita Acara Kejadian yang menghasilkan invoice ini.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('bak_id'):
                vals['invoice_date_due'] = False
                vals['invoice_payment_term_id'] = False
        return super().create(vals_list)

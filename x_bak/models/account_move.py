from odoo import models, fields


class AccountMove(models.Model):
    _inherit = 'account.move'

    bak_id = fields.Many2one(
        'bak',
        string='BAK Reference',
        readonly=True,
        copy=False,
        help='Referensi ke Berita Acara Kejadian yang menghasilkan invoice ini.',
    )

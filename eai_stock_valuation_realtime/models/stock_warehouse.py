from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    eai_rt_analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analitik Valuasi (butik)',
        check_company=True,
        help="Bila diisi, jurnal valuasi real-time dari gudang ini diberi analitik ini (100%). "
             "Dipakai untuk laporan persediaan/HPP per butik.")

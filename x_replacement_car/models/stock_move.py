from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    replacement_car = fields.Boolean(
        string='Replacement Car',
        readonly=True,
        copy=False,
        default=False,
        help='Otomatis dicentang saat Delivery Order (DO) berstatus Done.'
    )
    # x_rc_analytic_distribution dihapus — RC menggunakan x_spk_analytic_distribution
    # yang sudah di-handle oleh x_spk module (_get_analytic_distribution override).
    # Satu field, satu kolom di view, sumber data sama: analytic account kendaraan.
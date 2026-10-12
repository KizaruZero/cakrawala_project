from odoo import api, fields, models


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    product_id = fields.Many2one(
        'product.product',
        string='Product',
        compute='_compute_product_id',
        store=False,
        help='Otomatis diambil dari Fleet Number (stock.lot) kendaraan. '
             'Digunakan untuk Goods Issue pada proses Replacement Car.',
    )

    @api.depends('lot_id.product_id')
    def _compute_product_id(self):
        for vehicle in self:
            vehicle.product_id = vehicle.lot_id.product_id

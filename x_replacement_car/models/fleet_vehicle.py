from odoo import api, fields, models


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    product_id = fields.Many2one(
        'product.product',
        string='Product',
        compute='_compute_product_id',
        store=True,
        help='Otomatis diambil dari Serial Number (stock.lot) '
             'yang terhubung via Asset Number. '
             'Digunakan untuk Goods Issue pada proses Replacement Car.',
    )

    @api.depends('asset_number')
    def _compute_product_id(self):
        StockLot = self.env['stock.lot']
        for vehicle in self:
            if vehicle.asset_number:
                lot = StockLot.search(
                    [('name', '=', vehicle.asset_number)], limit=1
                )
                vehicle.product_id = lot.product_id if lot else False
            else:
                vehicle.product_id = False

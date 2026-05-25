from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain=[('type', 'in', ['consu', 'product'])],
        help='Produk yang merepresentasikan kendaraan ini untuk keperluan '
             'stock move (Good Issue) pada proses Replacement Car.',
    )

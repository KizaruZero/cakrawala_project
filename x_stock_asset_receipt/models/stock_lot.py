from odoo import fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    initial_license_plate = fields.Char(string='Initial License Plate')
    chassis_number = fields.Char(string='Chassis Number')
    engine_number = fields.Char(string='Engine Number')

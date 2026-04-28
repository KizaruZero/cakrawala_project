from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    engine_number = fields.Char(string='Engine Number', tracking=True)

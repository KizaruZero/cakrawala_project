from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    asset_number = fields.Char(string="Asset Number")

from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    # Used by disposal (and may overlap with other fleet extensions, e.g. x_service_planning).
    asset_number = fields.Char(string="Asset Number")

from odoo import models, fields

class VehicleColor(models.Model):
    _name = 'vehicle.color'
    _description = 'Vehicle Color'

    name = fields.Char(string='Color Name', required=True)
    active = fields.Boolean(default=True)

class VehicleYear(models.Model):
    _name = 'vehicle.year'
    _description = 'Vehicle Year'

    name = fields.Char(string='Year', required=True)
    active = fields.Boolean(default=True)

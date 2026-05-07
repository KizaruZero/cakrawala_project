from odoo import models, fields

class FleetServiceType(models.Model):
    _inherit = 'fleet.service.type'

    is_license_plate = fields.Boolean(string="Is License Plate", default=True)
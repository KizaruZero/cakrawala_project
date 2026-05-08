from odoo import models, api

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('license_plate') and vals.get('initial_license_plate'):
                vals['license_plate'] = vals['initial_license_plate']
        return super().create(vals_list)

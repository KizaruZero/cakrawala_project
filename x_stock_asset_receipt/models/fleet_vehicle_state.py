from odoo import models, fields, api

class FleetVehicleState(models.Model):
    _inherit = 'fleet.vehicle.state'

    is_first_destination = fields.Boolean(
        string='Is First Destination',
        default=False,
        help="If checked, this state will be used as the default pipeline when a Fleet is registered from GR."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_first_destination'):
                self.search([('is_first_destination', '=', True)]).write({'is_first_destination': False})
        return super(FleetVehicleState, self).create(vals_list)

    def write(self, vals):
        if vals.get('is_first_destination'):
            self.search([('is_first_destination', '=', True), ('id', '!=', self.id)]).write({'is_first_destination': False})
        return super(FleetVehicleState, self).write(vals)

from odoo import fields, models


class FleetVehicleLicensePlateHistory(models.Model):
    _name = 'fleet.vehicle.license.plate.history'
    _description = 'Fleet Vehicle License Plate History'
    _order = 'valid_from desc, id desc'

    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Vehicle',
        required=True,
        ondelete='cascade',
        index=True,
    )
    license_plate = fields.Char(string='Plate Number', required=True)
    valid_from = fields.Date(string='Valid From')
    valid_until = fields.Date(string='Valid Until')

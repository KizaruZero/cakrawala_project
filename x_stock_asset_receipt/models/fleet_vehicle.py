from odoo import models, fields


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    fleet_sub_status_id = fields.Many2one(
        'vehicle.substatus',
        string='Fleet Sub-Status',
        ondelete='restrict',
    )
    asset_type = fields.Char(string='Asset Type')
    asset_number = fields.Char(string='Asset Number')
    unit_classification = fields.Char(string='Unit Classification')
    assignment_date = fields.Date(string='Assignment Date')
    plan_to_disposal = fields.Boolean(string='Plan to Disposal')
    initial_license_plate = fields.Char(string='Initial License Plate')
    chassis_number = fields.Char(string='Chassis Number')
    engine_number = fields.Char(string='Engine Number')

from odoo import fields, models


class VehicleSubstatus(models.Model):
    _name = 'vehicle.substatus'
    _description = 'Vehicle Substatus'
    _order = 'sequence, name'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_disposal = fields.Boolean(
        string='Is Disposal',
        help='Vehicles with this sub-status appear in disposal vehicle selection.',
    )

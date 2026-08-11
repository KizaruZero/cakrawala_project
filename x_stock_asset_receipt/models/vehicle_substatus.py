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
    is_rental_type = fields.Boolean(
        string='Is Rental Type',
        help='Sub-statuses flagged here are selectable as Rental Type on Goods Receipt. '
             'The one chosen on the GR becomes the vehicle Fleet Sub-Status when the asset is registered.',
    )

from odoo import api, fields, models


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
        string='Is Fleet Sub-status',
        help='Sub-statuses flagged here are selectable as Fleet Sub-status on Goods Receipt. '
             'The one chosen on the GR becomes the vehicle Fleet Sub-Status when the asset is registered.',
    )
    is_replacement_car = fields.Boolean(
        string='Is Replacement Car',
        help='Vehicles with this sub-status can be picked as the replacement vehicle of a '
             'Replacement Car request, and a unit handed over as replacement car (Goods '
             'Issue) gets this sub-status. Its Parent Status is the status they must be in.',
    )
    state_id = fields.Many2one(
        'fleet.vehicle.state',
        string='Parent Status',
        ondelete='restrict',
        help='Main fleet status this sub-status belongs to. A vehicle with this sub-status '
             'must be in this status; automated flows set the status from it.',
    )

    @api.model
    def _get_replacement_car_substatus(self):
        """The sub-status a unit gets when handed over as replacement car: the first
        one flagged Is Replacement Car (by sequence)."""
        return self.search([('is_replacement_car', '=', True)], limit=1)

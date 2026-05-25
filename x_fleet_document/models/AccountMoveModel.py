from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    x_fleet_contract_ids = fields.Many2many(
        'fleet.vehicle.log.contract',
        'fleet_contract_account_move_rel',
        'move_id',
        'contract_id',
        string='Fleet Documents/Contracts',
        copy=False,
    )

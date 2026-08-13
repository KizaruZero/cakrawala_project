from odoo import models, fields

class BastkType(models.Model):
    _name = 'bastk.type'
    _description = 'BASTK Type'

    name = fields.Char(required=True)
    is_disposal = fields.Boolean(string="Is Disposal")
    is_disabled_after_submitted_in = fields.Boolean(string="Is Disabled after Submitted In")
    need_submit_out = fields.Boolean(string="Need Submit Out", default=True)
    need_submit_in = fields.Boolean(string="Need Submit In", default=True)
    need_gi = fields.Boolean(string="Need GI")
    need_gr = fields.Boolean(string="Need GR")
    
    out_state_id = fields.Many2one('fleet.vehicle.state', string='State when Out')
    out_substate_id = fields.Many2one('vehicle.substatus', string='Substate when Out')
    in_state_id = fields.Many2one('fleet.vehicle.state', string='State when In')
    in_substate_id = fields.Many2one('vehicle.substatus', string='Substate when In')
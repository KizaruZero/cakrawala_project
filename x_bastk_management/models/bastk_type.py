from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

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
    gi_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='GI Operation Type',
        domain=[('code', '=', 'outgoing')],
    )
    gr_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='GR Operation Type',
        domain=[('code', '=', 'incoming')],
    )
    
    out_state_id = fields.Many2one('fleet.vehicle.state', string='State when Out')
    out_substate_id = fields.Many2one('vehicle.substatus', string='Substate when Out')
    in_state_id = fields.Many2one('fleet.vehicle.state', string='State when In')
    in_substate_id = fields.Many2one('vehicle.substatus', string='Substate when In')

    @api.onchange('need_submit_out')
    def _onchange_need_submit_out(self):
        if not self.need_submit_out:
            self.need_gi = False
            self.need_gr = False
            self.gi_picking_type_id = False
            self.gr_picking_type_id = False

    @api.constrains('need_submit_out', 'need_submit_in', 'need_gr')
    def _check_need_gr_validity(self):
        for rec in self:
            if not rec.need_submit_out and rec.need_submit_in and rec.need_gr:
                raise ValidationError(_(
                    "Tipe BASTK tidak valid: BASTK yang tidak memerlukan Submit Out "
                    "tidak dapat mengaktifkan Goods Receive (GR). Kasus ini tidak diperbolehkan."
                ))
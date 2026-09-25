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

    @api.constrains('out_state_id', 'out_substate_id', 'in_state_id', 'in_substate_id')
    def _check_state_substate_mapping(self):
        """The configured State must be the Parent Status of the configured Substate."""
        for rec in self:
            for label, state, sub in (
                (_('Out'), rec.out_state_id, rec.out_substate_id),
                (_('In'), rec.in_state_id, rec.in_substate_id),
            ):
                if state and sub.state_id and sub.state_id != state:
                    raise ValidationError(_(
                        "BASTK Type %(type)s (%(dir)s): Substate '%(sub)s' belongs to Status "
                        "'%(parent)s', not '%(state)s'.",
                        type=rec.name, dir=label, sub=sub.name,
                        parent=sub.state_id.name, state=state.name,
                    ))

    @api.onchange('out_substate_id')
    def _onchange_out_substate_id(self):
        if self.out_substate_id.state_id:
            self.out_state_id = self.out_substate_id.state_id

    @api.onchange('in_substate_id')
    def _onchange_in_substate_id(self):
        if self.in_substate_id.state_id:
            self.in_state_id = self.in_substate_id.state_id

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
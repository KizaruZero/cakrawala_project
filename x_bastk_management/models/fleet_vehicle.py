from odoo import fields, models, api


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    engine_number = fields.Char(string='Engine Number', tracking=True)
    bastk_count = fields.Integer(compute='_compute_bastk_count', string='BASTK Count')
    asset_type_id = fields.Many2one('bastk.asset.type', string='Asset Type')

    def _compute_bastk_count(self):
        for vehicle in self:
            vehicle.bastk_count = self.env['bastk.management'].search_count([('vehicle_id', '=', vehicle.id)])

    def action_view_bastk(self):
        self.ensure_one()
        return {
            'name': 'BASTK',
            'view_mode': 'list,form',
            'res_model': 'bastk.management',
            'type': 'ir.actions.act_window',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
        }

class FleetVehicleState(models.Model):
    _inherit = 'fleet.vehicle.state'

    is_inactive_state = fields.Boolean(string="Is Inactive State", default=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_inactive_state'):
                self.search([('is_inactive_state', '=', True)]).write({'is_inactive_state': False})
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('is_inactive_state'):
            self.search([('is_inactive_state', '=', True), ('id', '!=', self.id)]).write({'is_inactive_state': False})
        return super().write(vals)

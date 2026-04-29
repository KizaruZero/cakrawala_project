from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    engine_number = fields.Char(string='Engine Number', tracking=True)
    bastk_count = fields.Integer(compute='_compute_bastk_count', string='BASTK Count')

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

from odoo import models, fields, api

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    bak_count = fields.Integer(compute='_compute_bak_count', string='BAK Count')

    def _compute_bak_count(self):
        for vehicle in self:
            vehicle.bak_count = self.env['bak'].search_count([('vehicle_id', '=', vehicle.id)])

    def action_view_baks(self):
        self.ensure_one()
        return {
            'name': 'Berita Acara Kejadian (BAK)',
            'view_mode': 'list,form',
            'res_model': 'bak',
            'type': 'ir.actions.act_window',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
        }

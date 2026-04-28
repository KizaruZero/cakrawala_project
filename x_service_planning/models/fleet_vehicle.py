from odoo import models, fields

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    asset_number = fields.Char(string="Asset Number")
    engine_number = fields.Char(string="Engine Number")
    color = fields.Char(string="Color")

    service_planning_ids = fields.One2many(
        'service.planning',
        'vehicle_id',
        string="Service Planning"
    )

    service_planning_count = fields.Integer(
        compute='_compute_service_planning_count'
    )

    def _compute_service_planning_count(self):
        for rec in self:
            rec.service_planning_count = len(rec.service_planning_ids)

    def action_view_service_planning(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Service Planning',
            'res_model': 'service.planning',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
        }
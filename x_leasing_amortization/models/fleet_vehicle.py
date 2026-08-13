# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class FleetVehicle(models.Model):
    """Expose the leasing schedule(s) financing this vehicle as a smart button."""
    _inherit = 'fleet.vehicle'

    leasing_loan_ids = fields.One2many(
        'account.loan',
        'vehicle_id',
        string='Leasing Schedules',
    )
    leasing_loan_count = fields.Integer(
        string='Leasing Count',
        compute='_compute_leasing_loan_count',
    )

    @api.depends('leasing_loan_ids')
    def _compute_leasing_loan_count(self):
        for vehicle in self:
            vehicle.leasing_loan_count = len(vehicle.leasing_loan_ids)

    def action_view_leasing_schedule(self):
        """Open the leasing schedule(s) whose Vehicle is this record."""
        self.ensure_one()
        loans = self.leasing_loan_ids
        if len(loans) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Leasing Schedule'),
                'res_model': 'account.loan',
                'res_id': loans.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Leasing Schedules'),
            'res_model': 'account.loan',
            'view_mode': 'list,form',
            'domain': [('id', 'in', loans.ids)],
            'target': 'current',
        }

from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    bastk_id = fields.Many2one('bastk.management', string='BASTK', copy=False)
    bastk_date = fields.Date(string='BASTK Date', compute='_compute_bastk_date', store=True, readonly=True)

    @api.depends('bastk_id.state', 'bastk_id.start_date', 'bastk_id.end_date')
    def _compute_bastk_date(self):
        for rec in self:
            if rec.bastk_id:
                if rec.bastk_id.state == 'submitted_outside':
                    rec.bastk_date = rec.bastk_id.start_date
                elif rec.bastk_id.state in ('submitted_inside', 'done'):
                    rec.bastk_date = rec.bastk_id.end_date
                else:
                    rec.bastk_date = rec.bastk_id.start_date
            else:
                rec.bastk_date = False

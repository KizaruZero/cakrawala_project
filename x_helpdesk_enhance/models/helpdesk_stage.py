# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

class HelpdeskStage(models.Model):
    _inherit = 'helpdesk.stage'

    is_close_stage = fields.Boolean(string='Is Close Stage', help='Check this if this stage is considered a closed stage.')
    close_user_ids = fields.Many2many(
        'res.users',
        string='Authorized Close Users',
        help='Users authorized to move tickets to this closed stage. If empty, only admin can close.'
    )
    can_create_bak_or_spk = fields.Boolean(
        string='Can Create BAK/SPK',
        help='If checked, the "Create BAK" and "Create SPK" buttons will be visible in this stage.'
    )
    can_create_rc = fields.Boolean(
        string='Can Create RC',
        help='If checked, the "Create RC" button will be visible for tickets in this stage.'
    )
    is_completed = fields.Boolean(
        string='Is Completed',
        help='The final stage: entering it sets the Tanggal Selesai of the ticket, '
             'and a ticket in it can no longer be moved to another stage. Only one stage can have it.',
    )

    @api.constrains('is_completed', 'active')
    def _check_single_completed_stage(self):
        if self.filtered('is_completed') and self.search_count([('is_completed', '=', True)]) > 1:
            raise ValidationError("Hanya boleh ada satu stage dengan Is Completed.")

    @api.model
    def _link_completed_stage_to_teams(self):
        """Every team uses the Completed stage (called on install and by the 19.0.1.0.9 migration)."""
        stage = self.search([('is_completed', '=', True)], limit=1)
        if stage:
            teams = self.env['helpdesk.team'].with_context(active_test=False).search([])
            teams.sudo().write({'stage_ids': [(4, stage.id)]})

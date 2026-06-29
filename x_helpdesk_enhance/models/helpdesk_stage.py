# -*- coding: utf-8 -*-
from odoo import models, fields

class HelpdeskStage(models.Model):
    _inherit = 'helpdesk.stage'

    is_close_stage = fields.Boolean(string='Is Close Stage', help='Check this if this stage is considered a closed stage.')
    close_user_ids = fields.Many2many(
        'res.users',
        string='Authorized Close Users',
        help='Users authorized to move tickets to this closed stage. If empty, only admin can close.'
    )

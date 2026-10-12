# -*- coding: utf-8 -*-
from odoo import models, fields

class CrmStage(models.Model):
    _inherit = 'crm.stage'

    can_create_rc = fields.Boolean(
        string='Can Create RC',
        help='If checked, opportunities/leads in this stage can create a Replacement Car.'
    )

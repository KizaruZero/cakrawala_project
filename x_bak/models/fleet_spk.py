# -*- coding: utf-8 -*-
from odoo import models, fields

class FleetSPK(models.Model):
    _inherit = 'fleet.spk'

    bak_id = fields.Many2one('bak', string="BAK Form Number")

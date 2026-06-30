# -*- coding: utf-8 -*-
from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    fleet_spk_id = fields.Many2one('fleet.spk', string='SPK Reference', copy=False)

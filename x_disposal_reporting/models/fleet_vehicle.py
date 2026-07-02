# -*- coding: utf-8 -*-
from odoo import models, fields

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    sub_type = fields.Char(string='Sub-Type', tracking=True)

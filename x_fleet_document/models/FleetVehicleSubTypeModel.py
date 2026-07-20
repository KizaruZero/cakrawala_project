# -*- coding: utf-8 -*-
from odoo import fields, models


class FleetVehicleSubType(models.Model):
    _name = 'fleet.vehicle.sub.type'
    _description = 'Fleet Vehicle Sub-Type'
    _order = 'name'

    name = fields.Char(string='Name', required=True, translate=True)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'Sub-Type name already exists!',
    )

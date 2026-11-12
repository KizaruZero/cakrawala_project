# -*- coding: utf-8 -*-
from odoo import fields, models


class FleetInsuranceCoverage(models.Model):
    _name = 'fleet.insurance.coverage'
    _description = 'Jaminan Pertanggungan Asuransi'
    _order = 'name'

    name = fields.Char(string='Jaminan Pertanggungan', required=True, translate=True)
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint('UNIQUE(name)', 'Jaminan Pertanggungan ini sudah ada.')

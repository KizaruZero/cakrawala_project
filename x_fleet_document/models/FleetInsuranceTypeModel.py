# -*- coding: utf-8 -*-
from odoo import fields, models


class FleetInsuranceType(models.Model):
    _name = 'fleet.insurance.type'
    _description = 'Tipe Asuransi'
    _order = 'sequence, name'

    name = fields.Char(string='Tipe Asuransi', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint('UNIQUE(name)', 'Tipe Asuransi ini sudah ada.')

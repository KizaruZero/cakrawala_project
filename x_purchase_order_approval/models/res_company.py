# -*- coding: utf-8 -*-

from datetime import datetime
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'
    
    company_code = fields.Char(string='Company Code', required=True)
    footer_logo_binary = fields.Binary(string='Footer Logo', attachment=True)
    footer_logo_binary_name = fields.Char(string='Footer Logo Name')
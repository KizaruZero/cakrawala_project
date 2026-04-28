# -*- coding: utf-8 -*-

from datetime import datetime
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    is_general_vendor = fields.Boolean("Is General Vendor", default=False)
# -*- coding: utf-8 -*-

from datetime import datetime
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    line_no = fields.Char(string='Line No')
    remark = fields.Char(string='Remark')
# -*- coding: utf-8 -*-
from odoo import models, fields

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    bastk_id = fields.Many2one(
        'bastk.management',
        string='BASTK Reference',
        help='Optional BASTK reference for this Delivery Order.'
    )

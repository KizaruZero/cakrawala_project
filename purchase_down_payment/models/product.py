# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_biaya_tdp = fields.Boolean(
        string='Biaya Biaya TDP',
        default=False,
        help='Centang jika produk ini merupakan komponen biaya TDP untuk Down Payment PO Leasing.',
    )

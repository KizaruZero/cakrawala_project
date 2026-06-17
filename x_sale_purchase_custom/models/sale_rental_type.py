# -*- coding: utf-8 -*-
from odoo import models, fields

class SaleRentalType(models.Model):
    _name = 'sale.rental.type'
    _description = 'Sale Rental Type'

    name = fields.Char(string='Name', required=True)
    is_related_pr = fields.Boolean(string='Related PR', default=False, help="If checked, allows creating a Purchase Request from Sales Order.")
    is_related_po = fields.Boolean(string='Related PO', default=False, help="If checked, allows creating a Purchase Order from Sales Order.")

# -*- coding: utf-8 -*-
from odoo import fields, models

class PurchaseOrderTypeMaster(models.Model):
    _inherit = "purchase.order.type.master"

    is_leasing = fields.Boolean(string='Is Leasing', default=False, help="Identify if this PO type is for Leasing.")

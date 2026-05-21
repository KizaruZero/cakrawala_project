# -*- coding: utf-8 -*-
from odoo import models, fields

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    sale_order_id = fields.Many2one('sale.order', string='Sales Order Related', readonly=True)
    customer_so_related = fields.Char(string='Customer SO Related', readonly=True)
    rental_type_id = fields.Many2one('sale.rental.type', string='Rental Type', readonly=True)
    rpc = fields.Char(string='RPC')

    def _compute_display_name(self):
        super()._compute_display_name()
        if self.env.context.get('show_only_name'):
            for po in self:
                po.display_name = po.name

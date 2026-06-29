# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    x_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account (Text)',
        compute='_compute_x_analytic_account_id',
        inverse='_inverse_x_analytic_account_id',
        store=True,
        help="Field jembatan untuk mempermudah Export/Import data Analytic Account."
    )

    @api.depends('analytic_distribution')
    def _compute_x_analytic_account_id(self):
        for line in self:
            if line.analytic_distribution:
                try:
                    first_account_id = list(line.analytic_distribution.keys())[0]
                    line.x_analytic_account_id = int(first_account_id)
                except Exception:
                    line.x_analytic_account_id = False
            else:
                line.x_analytic_account_id = False

    def _inverse_x_analytic_account_id(self):
        for line in self:
            if line.x_analytic_account_id:
                line.analytic_distribution = {str(line.x_analytic_account_id.id): 100}
            else:
                line.analytic_distribution = False

    @api.onchange('x_analytic_account_id')
    def _onchange_x_analytic_account_id(self):
        if self.x_analytic_account_id:
            self.analytic_distribution = {str(self.x_analytic_account_id.id): 100}
        else:
            self.analytic_distribution = False


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

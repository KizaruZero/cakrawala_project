from odoo import models

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_procurement_values(self, **kwargs):
        vals = super()._prepare_procurement_values(**kwargs)
        if self.order_id.analytic_account_id:
            vals['analytic_account_id'] = self.order_id.analytic_account_id.id
        return vals

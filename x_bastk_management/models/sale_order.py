from odoo import models

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_procurement_values(self, **kwargs):
        vals = super()._prepare_procurement_values(**kwargs)
        if self.analytic_distribution:
            vals['analytic_distribution'] = self.analytic_distribution
            try:
                first_account_id = next(iter(self.analytic_distribution.keys()))
                vals['analytic_account_id'] = int(first_account_id)
            except Exception:
                pass
        return vals

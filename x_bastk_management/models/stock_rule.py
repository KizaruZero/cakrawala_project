from odoo import models

class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _get_stock_move_values(self, *args, **kwargs):
        res = super()._get_stock_move_values(*args, **kwargs)
        # Extract 'values' from kwargs if present, otherwise it's the 8th positional argument (index 7)
        values = kwargs.get('values')
        if not values and len(args) >= 7:
            values = args[7] if len(args) > 7 else args[-1]
            
        if isinstance(values, dict) and values.get('analytic_account_id'):
            res['analytic_account_id'] = values['analytic_account_id']
        return res

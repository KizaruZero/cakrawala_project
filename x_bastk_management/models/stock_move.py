from odoo import models, fields

class StockMove(models.Model):
    _inherit = 'stock.move'

    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')

    def _prepare_move_line_vals(self, quantity=None, reserved_quant=None):
        vals = super()._prepare_move_line_vals(quantity=quantity, reserved_quant=reserved_quant)
        if self.analytic_account_id:
            vals['analytic_account_id'] = self.analytic_account_id.id
        return vals

    def _prepare_account_move_line(self, qty, cost, credit_account_id, debit_account_id, description):
        res = super()._prepare_account_move_line(qty, cost, credit_account_id, debit_account_id, description)
        if self.analytic_account_id:
            for line_vals in res:
                if isinstance(line_vals, tuple) and len(line_vals) == 3 and isinstance(line_vals[2], dict):
                    if 'analytic_distribution' not in line_vals[2] or not line_vals[2]['analytic_distribution']:
                        line_vals[2]['analytic_distribution'] = {str(self.analytic_account_id.id): 100.0}
        return res

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')

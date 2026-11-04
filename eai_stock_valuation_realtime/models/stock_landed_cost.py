from collections import defaultdict

from odoo import models


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    def button_validate(self):
        # Siapkan akun lawan per receipt bertanda, lalu biarkan standar menulis nilai move.
        # Mesin valuasi real-time menjurnal delta nilai receipt ke akun-akun ini.
        cost_without_lines = self.filtered(lambda c: not c.valuation_adjustment_lines)
        if cost_without_lines:
            cost_without_lines.compute_landed_cost()
        counterparts = defaultdict(lambda: defaultdict(float))
        for line in self.valuation_adjustment_lines.filtered('move_id'):
            move = line.move_id
            if not move._eai_rt_is_enabled() or not line.quantity:
                continue
            account = line._eai_rt_landed_cost_account()
            # Porsi qty yang masih di stok (standar Odoo 19 `_create_account_move_line`).
            remaining_qty = move.remaining_qty
            counterparts[move.id][account.id] += line.additional_landed_cost * (remaining_qty / line.quantity)
        extra = {
            move_id: list(by_account.items()) for move_id, by_account in counterparts.items()
        }
        return super(StockLandedCost, self.with_context(eai_rt_extra_counterparts=extra)).button_validate()


class StockValuationAdjustmentLines(models.Model):
    _inherit = 'stock.valuation.adjustment.lines'

    def _eai_rt_landed_cost_account(self):
        self.ensure_one()
        cost_product = self.cost_line_id.product_id
        return self.cost_line_id.account_id or cost_product._get_product_accounts()['expense']

    def _create_accounting_entries(self, remaining_qty):
        # Kategori bertanda: jurnal dibuat oleh mesin valuasi real-time, bukan di sini.
        if self.move_id and self.move_id._eai_rt_is_enabled():
            return []
        return super()._create_accounting_entries(remaining_qty)

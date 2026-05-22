# -*- coding: utf-8 -*-
# Propagate Fleet SPK sparepart analytic (or vehicle fallback) to stock valuation analytic.

from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    x_spk_analytic_distribution = fields.Json(
        string="SPK Analytic Distribution",
        copy=False,
        help="Filled when Internal SPK creates this goods-issue move (from sparepart line analytic "
             "or vehicle analytic). Consumed by _get_analytic_distribution for analytic lines.",
    )

    x_spk_analytic_account_ids = fields.Many2many(
        "account.analytic.account",
        string="Analytic Accounts (SPK)",
        compute="_compute_x_spk_analytic_account_ids",
        inverse="_inverse_x_spk_analytic_account_ids",
        store=False,
        help="Human-readable display of analytic accounts set via SPK analytic distribution.",
    )

    @api.depends("x_spk_analytic_distribution")
    def _compute_x_spk_analytic_account_ids(self):
        for move in self:
            dist = move.x_spk_analytic_distribution or {}
            ids = []
            for key in dist:
                try:
                    ids.extend(int(i) for i in str(key).split(",") if i.strip().isdigit())
                except (ValueError, AttributeError):
                    pass
            move.x_spk_analytic_account_ids = self.env["account.analytic.account"].browse(ids).exists()

    def _inverse_x_spk_analytic_account_ids(self):
        """Allow editing analytic accounts from the picking view; rebuild distribution at 100% each."""
        for move in self:
            accounts = move.x_spk_analytic_account_ids
            if not accounts:
                move.x_spk_analytic_distribution = False
            else:
                pct = round(100.0 / len(accounts), 2)
                move.x_spk_analytic_distribution = {str(acc.id): pct for acc in accounts}

    def _get_analytic_distribution(self):
        res = super()._get_analytic_distribution()
        custom = self.x_spk_analytic_distribution
        if not custom:
            return res if res else {}
        merged = dict(res or {})
        for key, pct in custom.items():
            merged[str(key)] = float(pct)
        return merged

# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = "stock.move"

    analytic_precision = fields.Integer(
        string="Analytic Precision",
        default=2,
    )

    x_spk_analytic_distribution = fields.Json(
        string="Analytic Distribution",
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
            if move._is_fleet_delivery_move():
                source_lot = move._fleet_source_lot()
                if source_lot and accounts != source_lot.analytic_account_id:
                    raise UserError(move._fleet_source_lock_message())
                if move.state in ('draft', 'waiting', 'done', 'cancel'):
                    move._write_fleet_analytic_distribution(move._normalize_analytic_weights(
                        {str(acc.id): 1 for acc in accounts}))
                else:
                    move._assign_fleet_lots_from_accounts(accounts, strict=True)
                    if move.move_line_ids.filtered('lot_id'):
                        move._sync_fleet_analytic_from_lines()
                    else:
                        move._write_fleet_analytic_distribution(False)
                continue
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

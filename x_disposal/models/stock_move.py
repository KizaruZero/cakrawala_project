from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    x_disposal_analytic_distribution = fields.Json(
        string="Disposal Analytic Distribution",
        copy=False,
        help="Filled from the vehicle analytic account when a disposal Sales Order creates this delivery.",
    )
    x_disposal_analytic_account_ids = fields.Many2many(
        "account.analytic.account",
        string="Analytic Accounts (Disposal)",
        compute="_compute_x_disposal_analytic_account_ids",
        store=False,
    )
    x_disposal_is_delivery = fields.Boolean(
        string="Is Disposal Delivery",
        compute="_compute_x_disposal_is_delivery",
        store=False,
    )

    @api.depends("picking_id.disposal_bidding_id")
    def _compute_x_disposal_is_delivery(self):
        for move in self:
            move.x_disposal_is_delivery = bool(move.picking_id.disposal_bidding_id)

    @api.depends("x_disposal_analytic_distribution")
    def _compute_x_disposal_analytic_account_ids(self):
        for move in self:
            ids = []
            for key in move.x_disposal_analytic_distribution or {}:
                ids.extend(int(value) for value in str(key).split(",") if value.strip().isdigit())
            move.x_disposal_analytic_account_ids = self.env["account.analytic.account"].browse(ids).exists()

    def _get_analytic_distribution(self):
        try:
            res = super()._get_analytic_distribution()
        except AttributeError:
            res = {}
        custom = self.x_disposal_analytic_distribution
        if not custom:
            return res if res else {}
        merged = dict(res or {})
        for key, pct in custom.items():
            merged[str(key)] = float(pct)
        return merged

    def _set_disposal_lot(self, lot):
        for move in self:
            if not lot or move.state in ("done", "cancel"):
                continue
            if move.product_id != lot.product_id:
                continue

            if move.lot_ids != lot:
                move.lot_ids = [(6, 0, [lot.id])]

            for line in move.move_line_ids.filtered(lambda sml: sml.lot_id == lot):
                line.write({
                    "initial_license_plate": lot.initial_license_plate or False,
                    "chassis_number": lot.chassis_number or False,
                    "engine_number": lot.engine_number or False,
                })

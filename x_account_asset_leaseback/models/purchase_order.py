from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    asset_id = fields.Many2one("account.asset", string="Asset Link", tracking=True)


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    def _get_received_vehicle(self):
        """Vehicle received on this line: the Fleet of the serial booked on its Goods Receipt."""
        self.ensure_one()
        moves = self.move_ids.filtered(
            lambda m: m.state == "done" and m.picking_code == "incoming" and not m.origin_returned_move_id
        )
        vehicles = moves.move_line_ids.lot_id.sudo().fleet_vehicle_id
        return vehicles if len(vehicles) == 1 else self.env["fleet.vehicle"]

    def _prepare_account_move_line(self, move=False):
        res = super()._prepare_account_move_line(move=move)
        if not self.display_type and self.product_id.is_vehicle:
            vehicle = self._get_received_vehicle()
            if vehicle:
                res["vehicle_id"] = vehicle.id
        return res

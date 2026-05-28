from odoo import fields, models
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    disposal_bidding_id = fields.Many2one(
        "disposal.bidding",
        string="Disposal Bidding",
        readonly=True,
        copy=False,
    )
    disposal_vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Disposal Vehicle",
        readonly=True,
        copy=False,
    )

    def action_assign(self):
        res = super().action_assign()
        self._sync_disposal_lots_from_bidding()
        return res

    def _sync_disposal_lots_from_bidding(self, raise_if_missing=False):
        for picking in self.filtered("disposal_bidding_id"):
            lot = picking.disposal_bidding_id._get_vehicle_stock_lot()
            if not lot:
                if raise_if_missing:
                    raise ValidationError(
                        "Serial number kendaraan disposal tidak ditemukan. "
                        "Pastikan Asset Number kendaraan sama dengan Serial/Lot stock."
                    )
                continue

            moves = picking.move_ids.filtered(lambda move: move.product_id == lot.product_id)
            if not moves and raise_if_missing:
                raise ValidationError(
                    "Product pada delivery disposal tidak sama dengan product serial kendaraan (%s)."
                    % lot.product_id.display_name
                )
            moves._set_disposal_lot(lot)

    def button_validate(self):
        self._sync_disposal_lots_from_bidding(raise_if_missing=True)
        res = super().button_validate()
        sold_status = self.env.ref("x_stock_asset_receipt.vehicle_substatus_sold", raise_if_not_found=False)
        if not sold_status:
            sold_status = self.env["vehicle.substatus"].search([("name", "=", "Sold")], limit=1)

        for picking in self.filtered(lambda p: p.state == "done" and p.disposal_vehicle_id):
            if sold_status:
                picking.disposal_vehicle_id.sudo().write({"fleet_sub_status_id": sold_status.id})
            if picking.disposal_bidding_id:
                picking.disposal_bidding_id.message_post(
                    body="Delivery %s is done. Fleet sub-status changed to Sold." % picking.name
                )
        return res

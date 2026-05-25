from odoo import fields, models


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

    def button_validate(self):
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

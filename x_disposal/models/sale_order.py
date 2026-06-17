from odoo import fields, models
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

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

    def action_confirm(self):
        disposal_orders = self.filtered("disposal_bidding_id")
        regular_orders = self - disposal_orders

        res = True
        if regular_orders:
            res = super(SaleOrder, regular_orders).action_confirm()
        if disposal_orders:
            res = super(SaleOrder, disposal_orders.with_context(x_disposal_skip_rental_type_check=True)).action_confirm()

        for order in disposal_orders:
            order._sync_disposal_to_delivery()
        return res

    def _sync_disposal_to_delivery(self):
        for order in self:
            analytic_distribution = order.disposal_bidding_id._get_vehicle_analytic_distribution()
            disposal_lot = order.disposal_bidding_id._get_vehicle_stock_lot()
            if not disposal_lot:
                raise ValidationError(
                    "Serial number kendaraan disposal tidak ditemukan. "
                    "Pastikan Asset Number kendaraan sama dengan Serial/Lot stock."
                )

            for picking in order.picking_ids:
                picking.write({
                    "disposal_bidding_id": order.disposal_bidding_id.id,
                    "disposal_vehicle_id": order.disposal_vehicle_id.id,
                })
                for move in picking.move_ids.filtered(lambda m: m.sale_line_id.order_id == order):
                    if move.product_id != disposal_lot.product_id:
                        raise ValidationError(
                            "Product pada delivery disposal (%s) tidak sama dengan product serial kendaraan (%s)."
                            % (move.product_id.display_name, disposal_lot.product_id.display_name)
                        )

                    vals = {}
                    if "x_disposal_analytic_distribution" in move._fields and analytic_distribution:
                        vals["x_disposal_analytic_distribution"] = analytic_distribution
                    if "analytic_distribution" in move._fields and analytic_distribution:
                        vals["analytic_distribution"] = analytic_distribution
                    if vals:
                        move.write(vals)
                    move._set_disposal_lot(disposal_lot)

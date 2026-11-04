from odoo import api, fields, models


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    asset_number = fields.Char(string="Asset Number")
    disposal_sale_order_ids = fields.One2many("sale.order", "disposal_vehicle_id", string="Disposal Sales Orders")
    disposal_start_date = fields.Date(
        string="Disposal Start Date",
        compute="_compute_disposal_start_date",
        store=True,
        help="Date the vehicle moved to a sub status flagged Is Disposal.",
    )
    disposal_end_date = fields.Date(
        string="Disposal End Date",
        compute="_compute_disposal_end_date",
        store=True,
        help="Date the vehicle is Sold and every invoice of its delivered disposal sale is paid, whichever comes last. "
             "A vehicle Sold without a disposal delivery ends on the day it is Sold.",
    )
    disposal_aging = fields.Integer(
        string="Aging Disposal (Days)",
        compute="_compute_disposal_aging",
        help="Days since the Disposal Start Date, up to the Disposal End Date once there is one.",
    )

    @api.depends("fleet_sub_status_id")
    def _compute_disposal_start_date(self):
        for vehicle in self:
            sub_status = vehicle.fleet_sub_status_id
            if sub_status.is_disposal:
                vehicle.disposal_start_date = vehicle.disposal_start_date or fields.Date.context_today(vehicle)
            elif sub_status.is_sold:
                vehicle.disposal_start_date = vehicle.disposal_start_date
            else:
                vehicle.disposal_start_date = False

    @api.depends(
        "fleet_sub_status_id",
        "disposal_start_date",
        "disposal_sale_order_ids.invoice_status",
        "disposal_sale_order_ids.picking_ids.state",
        "disposal_sale_order_ids.picking_ids.date_done",
        "disposal_sale_order_ids.order_line.invoice_lines.move_id.state",
        "disposal_sale_order_ids.order_line.invoice_lines.move_id.payment_state",
        "disposal_sale_order_ids.order_line.invoice_lines.move_id.matched_payment_ids.date",
    )
    def _compute_disposal_end_date(self):
        for vehicle in self:
            vehicle.disposal_end_date = vehicle._get_disposal_end_date()

    def _get_disposal_end_date(self):
        self.ensure_one()
        if not self.disposal_start_date or not self.fleet_sub_status_id.is_sold:
            return False

        deliveries = self.disposal_sale_order_ids.picking_ids.filtered(
            lambda picking: picking.state == "done" and picking.picking_type_code == "outgoing"
        )
        if not deliveries:
            return self.disposal_end_date or fields.Date.context_today(self)

        orders = deliveries.sale_id
        if not orders._is_fully_paid():
            return False

        invoices = orders._get_payable_invoices()
        payments = invoices.matched_payment_ids.filtered(lambda payment: payment.state in ("in_process", "paid"))
        payment_dates = payments.mapped("date") or invoices._get_reconciled_amls().mapped("date")
        delivery_dates = [fields.Date.context_today(self, picking.date_done) for picking in deliveries]
        return max(delivery_dates + payment_dates)

    @api.depends("disposal_start_date", "disposal_end_date")
    def _compute_disposal_aging(self):
        today = fields.Date.context_today(self)
        for vehicle in self:
            start = vehicle.disposal_start_date
            vehicle.disposal_aging = ((vehicle.disposal_end_date or today) - start).days if start else 0

from odoo import models, fields


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    # One2many relations for history
    tyre_history_ids = fields.One2many(
        "fleet.vehicle.tyre.history",
        "vehicle_id",
        string="Tyre History",
        readonly=True,
    )
    aki_history_ids = fields.One2many(
        "fleet.vehicle.aki.history",
        "vehicle_id",
        string="AKI History",
        readonly=True,
    )

    # Smart button counts
    spk_count = fields.Integer(
        string="SPK Count",
        compute="_compute_spk_count",
    )

    engine_number = fields.Char(
        string="Engine Number",
        tracking=True,
        copy=False,
    )
    last_service = fields.Date(
        string="Last Service Date",
        tracking=True,
        copy=False,
    )

    def _compute_spk_count(self):
        for vehicle in self:
            vehicle.spk_count = self.env["fleet.spk"].search_count(
                [("vehicle_id", "=", vehicle.id)]
            )


class FleetVehicleTyreHistory(models.Model):
    _name = "fleet.vehicle.tyre.history"
    _description = "Fleet Vehicle Tyre History"
    _order = "date desc"

    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        ondelete="cascade",
    )
    spk_id = fields.Many2one(
        "fleet.spk",
        string="SPK Reference",
        required=True,
        ondelete="cascade",
    )
    spk_number = fields.Char(
        string="SPK Number",
        related="spk_id.name",
        store=True,
    )
    date = fields.Date(
        string="Date",
        default=fields.Date.today,
    )
    old_production_number = fields.Char(string="Old Production Number")
    new_production_number = fields.Char(string="New Production Number")
    product_description = fields.Text(string="Product Description")
    notes = fields.Text(string="Notes")


class FleetVehicleAkiHistory(models.Model):
    _name = "fleet.vehicle.aki.history"
    _description = "Fleet Vehicle AKI (Battery) History"
    _order = "date desc"

    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        ondelete="cascade",
    )
    spk_id = fields.Many2one(
        "fleet.spk",
        string="SPK Reference",
        required=True,
        ondelete="cascade",
    )
    spk_number = fields.Char(
        string="SPK Number",
        related="spk_id.name",
        store=True,
    )
    date = fields.Date(
        string="Date",
        default=fields.Date.today,
    )
    # serial_number = fields.Char(string="Serial Number")
    old_AKI_code = fields.Char(string="Old AKI Code")
    new_AKI_code = fields.Char(string="New AKI Code")
    product_description = fields.Text(string="Product Description")
    notes = fields.Text(string="Notes")

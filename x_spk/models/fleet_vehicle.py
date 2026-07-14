from odoo import api, fields, models


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
        string="ACCU History",
        readonly=True,
    )

    tyre_ids = fields.One2many(
        "fleet.vehicle.tyre",
        "vehicle_id",
        string="Active Tyres",
    )
    aki_ids = fields.One2many(
        "fleet.vehicle.aki",
        "vehicle_id",
        string="Active ACCUs",
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

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if not record.tyre_ids:
                positions = ["Front Left", "Front Right", "Rear Left", "Rear Right"]
                for pos in positions:
                    self.env["fleet.vehicle.tyre"].create({
                        "vehicle_id": record.id,
                        "position": pos,
                    })
            if not record.aki_ids:
                self.env["fleet.vehicle.aki"].create({
                    "vehicle_id": record.id,
                    "name": "ACCU 1",
                })
        return records

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
    _description = "Fleet Vehicle ACCU (Battery) History"
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
    old_AKI_code = fields.Char(string="Old ACCU Code")
    new_AKI_code = fields.Char(string="New ACCU Code")
    product_description = fields.Text(string="Product Description")
    notes = fields.Text(string="Notes")


class FleetVehicleTyre(models.Model):
    _name = "fleet.vehicle.tyre"
    _description = "Fleet Vehicle Active Tyre"

    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        ondelete="cascade",
    )
    position = fields.Char(string="Position", required=True)
    production_number = fields.Char(string="Production Number")
    product_id = fields.Many2one("product.product", string="Tyre Product")
    date = fields.Date(string="Last Changed Date")
    notes = fields.Text(string="Notes")


class FleetVehicleAki(models.Model):
    _name = "fleet.vehicle.aki"
    _description = "Fleet Vehicle Active ACCU"

    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(string="Name", required=True, default="ACCU 1")
    aki_code = fields.Char(string="ACCU Code")
    product_id = fields.Many2one("product.product", string="ACCU Product")
    date = fields.Date(string="Last Changed Date")
    notes = fields.Text(string="Notes")


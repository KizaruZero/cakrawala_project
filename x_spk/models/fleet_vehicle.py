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
    tyre_reference_ids = fields.One2many(
        "fleet.vehicle.tyre.reference",
        "vehicle_id",
        string="Tyre Reference",
    )
    aki_reference_ids = fields.One2many(
        "fleet.vehicle.aki.reference",
        "vehicle_id",
        string="ACCU Reference",
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
        for vals in vals_list:
            if "name" not in vals or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "fleet.vehicle.sequence"
                )
        records = super().create(vals_list)
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


class FleetVehicleTyreReference(models.Model):
    _name = "fleet.vehicle.tyre.reference"
    _description = "Fleet Vehicle Tyre Reference"

    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        ondelete="cascade",
    )
    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Product Description",
        domain="[('is_tyre', '=', True)]",
    )
    initial_production_number = fields.Char(string="Initial Production Number")
    notes = fields.Text(string="Notes")


class FleetVehicleAkiReference(models.Model):
    _name = "fleet.vehicle.aki.reference"
    _description = "Fleet Vehicle ACCU Reference"

    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        ondelete="cascade",
    )
    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Product Description",
        domain="[('is_aki', '=', True)]",
    )
    initial_aki_code = fields.Char(string="Initial ACCU Code")
    notes = fields.Text(string="Notes")


class FleetVehicleTyre(models.Model):
    _name = "fleet.vehicle.tyre"
    _description = "Fleet Vehicle Active Tyre"
    _rec_name = "production_number"

    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        ondelete="cascade",
    )
    production_number = fields.Char(string="Production Number")
    product_id = fields.Many2one("product.product", string="Tyre Product")
    product_description = fields.Text(string="Product Description")
    date = fields.Date(string="Last Changed Date")
    notes = fields.Text(string="Notes")


class FleetVehicleAki(models.Model):
    _name = "fleet.vehicle.aki"
    _description = "Fleet Vehicle Active ACCU"
    _rec_name = "aki_code"

    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        ondelete="cascade",
    )
    aki_code = fields.Char(string="ACCU Code")
    product_id = fields.Many2one("product.product", string="ACCU Product")
    product_description = fields.Text(string="Product Description")
    date = fields.Date(string="Last Changed Date")
    notes = fields.Text(string="Notes")


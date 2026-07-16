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

    def _get_reference_initial_value(self, reference_lines, product, value_field):
        """Initial tyre/ACCU value from the vehicle reference lines.

        Prefer a reference for the same product template; fall back to any
        reference that carries a value, since older vehicles were often
        registered with a single generic reference line.
        """
        candidates = reference_lines.filtered(lambda r: r[value_field])
        if product:
            same_product = candidates.filtered(
                lambda r: r.product_tmpl_id == product.product_tmpl_id
            )
            candidates = same_product or candidates
        return candidates[:1][value_field] if candidates else False

    def _get_last_tyre_production_number(self, product=None):
        """Production number currently on the vehicle, for a tyre replacement.

        Latest replacement recorded in the tyre history, or — when the vehicle
        has never had one — the initial production number it was registered with.
        The history carries no product reference, so it is matched per vehicle.
        """
        self.ensure_one()
        history = self.env["fleet.vehicle.tyre.history"].search(
            [
                ("vehicle_id", "=", self.id),
                ("new_production_number", "!=", False),
            ],
            order="date desc, id desc",
            limit=1,
        )
        if history:
            return history.new_production_number
        return self._get_reference_initial_value(
            self.tyre_reference_ids, product, "initial_production_number"
        )

    def _get_last_aki_code(self, product=None):
        """ACCU code currently on the vehicle, for an ACCU replacement.

        Mirrors _get_last_tyre_production_number.
        """
        self.ensure_one()
        history = self.env["fleet.vehicle.aki.history"].search(
            [
                ("vehicle_id", "=", self.id),
                ("new_AKI_code", "!=", False),
            ],
            order="date desc, id desc",
            limit=1,
        )
        if history:
            return history.new_AKI_code
        return self._get_reference_initial_value(
            self.aki_reference_ids, product, "initial_aki_code"
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


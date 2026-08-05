from odoo import api, fields, models


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    # Master Data / Additional Fields
    motor_number = fields.Char(string="Motor Number")
    cc = fields.Integer(string="CC")
    engine_category_id = fields.Many2one("fleet.engine.category", string="Engine Category")
    drive_train_category_id = fields.Many2one("fleet.drivetrain.category", string="Drive Train Category")
    construction_year = fields.Integer(string="Construction Year")
    gps = fields.Char(string="GPS")
    spare_key = fields.Char(string="Kunci Serep (Spare Key)")
    spare_key_location = fields.Char(string="Spare Key Location")
    transmission_id = fields.Many2one("fleet.transmission", string="Transmission")

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

    def _get_latest_tyre_numbers(self, product, limit=1):
        """Returns the latest production numbers for this vehicle and product template.
        Returns a list of strings.
        """
        self.ensure_one()
        # 1. Primary: from history
        history = self.env["fleet.vehicle.tyre.history"].search(
            [("vehicle_id", "=", self.id), ("new_production_number", "!=", False)],
            order="date desc, id desc"
        )
        if product:
            history = history.filtered(lambda h: h.product_id and h.product_id.product_tmpl_id == product.product_tmpl_id)
        
        numbers = [h.new_production_number for h in history]
        if len(numbers) < limit:
            # 2. Fallback: append from reference if history doesn't have enough
            refs = self.env["fleet.vehicle.tyre.reference"].search(
                [("vehicle_id", "=", self.id)], order="id asc"
            )
            if product:
                refs = refs.filtered(lambda r: r.product_tmpl_id == product.product_tmpl_id)
            
            # Find which ones were already replaced by checking all history for this vehicle
            all_history = self.env["fleet.vehicle.tyre.history"].search([("vehicle_id", "=", self.id)])
            replaced_numbers = set(h.old_production_number for h in all_history if h.old_production_number)
            
            for r in refs:
                if r.initial_production_number and r.initial_production_number not in replaced_numbers and r.initial_production_number not in numbers:
                    numbers.append(r.initial_production_number)
                    
        return numbers[:limit] if numbers else []

    def _get_last_tyre_production_number(self, product=None):
        """Returns the single latest production number for a product."""
        numbers = self._get_latest_tyre_numbers(product, limit=1)
        return numbers[0] if numbers else False

    def _get_latest_aki_codes(self, product, limit=1):
        """Returns the latest AKI codes for this vehicle and product template.
        Returns a list of strings.
        """
        self.ensure_one()
        history = self.env["fleet.vehicle.aki.history"].search(
            [("vehicle_id", "=", self.id), ("new_AKI_code", "!=", False)],
            order="date desc, id desc"
        )
        if product:
            history = history.filtered(lambda h: h.product_id and h.product_id.product_tmpl_id == product.product_tmpl_id)
            
        codes = [h.new_AKI_code for h in history]
        if len(codes) < limit:
            refs = self.env["fleet.vehicle.aki.reference"].search(
                [("vehicle_id", "=", self.id)], order="id asc"
            )
            if product:
                refs = refs.filtered(lambda r: r.product_tmpl_id == product.product_tmpl_id)
            
            all_history = self.env["fleet.vehicle.aki.history"].search([("vehicle_id", "=", self.id)])
            replaced_codes = set(h.old_AKI_code for h in all_history if h.old_AKI_code)
            
            for r in refs:
                if r.initial_aki_code and r.initial_aki_code not in replaced_codes and r.initial_aki_code not in codes:
                    codes.append(r.initial_aki_code)
            
        return codes[:limit] if codes else []

    def _get_last_aki_code(self, product=None):
        """Returns the single latest AKI code for a product."""
        codes = self._get_latest_aki_codes(product, limit=1)
        return codes[0] if codes else False


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
    product_id = fields.Many2one("product.product", string="Tyre Product", index=True)
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
    product_id = fields.Many2one("product.product", string="ACCU Product", index=True)
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

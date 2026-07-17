from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SPKProductLine(models.Model):
    _name = "spk.product.line"
    _inherit = ["spk.stock.forecast.mixin"]
    _description = "SPK Product Line (service and spare part / material)"

    spk_id = fields.Many2one(
        "fleet.spk",
        string="SPK",
        required=True,
        ondelete="cascade",
    )
    spk_category = fields.Selection(
        selection=[
            ("internal", "Internal"),
            ("external", "External"),
        ],
        string="SPK Category",
        compute="_compute_spk_category",
        store=True,
        readonly=True,
        help="Samakan dengan field Category di SPK; untuk memfilter produk (SPK Category di variant/template).",
    )

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        ondelete="restrict",
    )

    quantity = fields.Float(
        string="Quantity",
        default=1.0,
        required=True,
    )
    unit_price = fields.Float(
        string="Unit Price",
        required=True,
    )
    subtotal = fields.Float(
        string="Subtotal (with tax)",
        compute="_compute_subtotal",
        store=True,
    )
    subtotal_without_tax = fields.Float(
        string="Subtotal (before tax)",
        compute="_compute_subtotal",
        store=True,
    )
    tax_total = fields.Float(
        string="Total Tax",
        compute="_compute_subtotal",
        store=True,
    )

    description = fields.Text(string="Description")
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Account",
        help="Defaults from the vehicle on the SPK when you add a product; can be changed per line.",
    )
    product_uom_id = fields.Many2one("uom.uom", string="Unit of Measure")
    tax_ids = fields.Many2many("account.tax", string="Taxes")

    available_stock = fields.Float(
        string="Available Stock",
        related="product_id.qty_available",
        store=False,
    )
    stock_status = fields.Boolean(
        string="Stock Available",
        compute="_compute_stock_status",
    )

    is_service_line = fields.Boolean(
        string="Is Service",
        compute="_compute_is_service_line",
        store=True,
    )

    @api.depends("product_id", "product_id.type")
    def _compute_is_service_line(self):
        for rec in self:
            rec.is_service_line = bool(rec.product_id and rec.product_id.type == "service")

    @api.depends("spk_id", "spk_id.category")
    def _compute_spk_category(self):
        for line in self:
            line.spk_category = line.spk_id.category

    @api.depends("product_id", "quantity")
    def _compute_stock_status(self):
        for rec in self:
            rec.stock_status = rec.available_stock >= rec.quantity

    @api.depends("quantity", "unit_price", "tax_ids")
    def _compute_subtotal(self):
        for record in self:
            subtotal_before_tax = record.quantity * record.unit_price
            record.subtotal_without_tax = subtotal_before_tax
            total_tax_rate = 0.0
            if record.tax_ids:
                for tax in record.tax_ids:
                    if tax.amount_type == "percent":
                        total_tax_rate += tax.amount / 100.0
            tax_amount = subtotal_before_tax * total_tax_rate
            record.tax_total = tax_amount
            record.subtotal = subtotal_before_tax + tax_amount

    @api.model
    def _get_product_autofill_vals(self, product):
        """product is product.product."""
        return {
            "description": product.description_sale or product.display_name,
            "product_uom_id": product.uom_id.id,
            "unit_price": product.standard_price or product.list_price,
            "tax_ids": [(6, 0, product.supplier_taxes_id.ids)],
        }

    def _default_analytic_from_spk_vehicle(self):
        self.ensure_one()
        vehicle = self.spk_id.vehicle_id
        if vehicle and vehicle.analytic_account_id:
            return vehicle.analytic_account_id
        return False

    def _product_domain_for_spk(self, spk):
        """Domain for product picker; enforced again by _check_line_product_rules."""
        if not spk:
            return []
        cat_part = []
        if spk.category in ("internal", "external"):
            cat_part = ["|", ("product_tmpl_id.spk_category", "=", spk.category), ("product_tmpl_id.spk_category", "=", False)]
        if spk.maintenance_type_id.is_on_risk:
            return [("product_tmpl_id.is_on_risk", "=", True)] + cat_part
        type_or = (
            "|",
            ("type", "=", "service"),
            ("type", "in", ["product", "consu"]),
        )
        return [("product_tmpl_id.is_on_risk", "=", False)] + list(type_or) + cat_part

    @api.onchange("spk_id")
    def _onchange_spk_id_product_domain(self):
        domain = self._product_domain_for_spk(self.spk_id)
        return {"domain": {"product_id": domain}}

    @api.onchange("product_id")
    def _onchange_product_id(self):
        product = self.product_id
        if not product:
            return
        self.update(self._get_product_autofill_vals(product))
        if not self.analytic_account_id:
            self.analytic_account_id = self._default_analytic_from_spk_vehicle()

    def _verify_line_product_rules(self):
        """Server-side rules (shared by @api.constrains and SPK maintenance type changes)."""
        for line in self:
            if not line.product_id or not line.spk_id:
                continue
            tmpl = line.product_id.product_tmpl_id
            spk = line.spk_id
            if spk.category in ("internal", "external") and not tmpl.is_on_risk:
                # Only check/enforce spk_category if it is set on the product template
                if tmpl.spk_category and tmpl.spk_category != spk.category:
                    raise ValidationError(
                        _(
                            "Product «%s» must have SPK Category «%s» on its template "
                            "(current: «%s») for this SPK category «%s»."
                        )
                        % (
                            line.product_id.display_name,
                            spk.category,
                            tmpl.spk_category or _("(not set)"),
                            spk.category,
                        )
                    )
            if spk.maintenance_type_id.is_on_risk:
                if not tmpl.is_on_risk:
                    raise ValidationError(
                        _(
                            "Maintenance type '%s' only allows Own Risk products "
                            "(«%s» is not Own Risk)."
                        )
                        % (spk.maintenance_type_id.name, line.product_id.display_name)
                    )
            else:
                if tmpl.is_on_risk:
                    raise ValidationError(
                        _(
                            "Own Risk products can only be used when Maintenance Type is set to Own Risk "
                            "(product «%s»)."
                        )
                        % line.product_id.display_name
                    )
                ptype = line.product_id.type
                if ptype not in ("service", "product", "consu"):
                    raise ValidationError(
                        _("Product «%s» has type «%s» which is not allowed on SPK lines.")
                        % (line.product_id.display_name, ptype)
                    )

    @api.constrains("product_id", "spk_id")
    def _check_line_product_rules(self):
        self._verify_line_product_rules()

    def _sync_detail_lines(self):
        tyre_model = self.env["spk.tyre.line"]
        aki_model = self.env["spk.aki.line"]

        for line in self:
            if not line.spk_id:
                continue
            qty = max(int(line.quantity or 0), 0)
            is_tyre = bool(line.product_id and getattr(line.product_id, "is_tyre", False))
            is_aki = bool(line.product_id and getattr(line.product_id, "is_aki", False))

            tyre_details = tyre_model.search(
                [("spk_id", "=", line.spk_id.id), ("product_line_id", "=", line.id)],
                order="id asc",
            )
            if is_tyre and qty:
                if len(tyre_details) < qty:
                    for _ in range(qty - len(tyre_details)):
                        tyre_model.create(
                            {
                                "spk_id": line.spk_id.id,
                                "product_line_id": line.id,
                            }
                        )
                elif len(tyre_details) > qty:
                    tyre_details[qty:].unlink()
            else:
                tyre_details.unlink()

            aki_details = aki_model.search(
                [("spk_id", "=", line.spk_id.id), ("product_line_id", "=", line.id)],
                order="id asc",
            )
            if is_aki and qty:
                if len(aki_details) < qty:
                    for _ in range(qty - len(aki_details)):
                        aki_model.create(
                            {
                                "spk_id": line.spk_id.id,
                                "product_line_id": line.id,
                            }
                        )
                elif len(aki_details) > qty:
                    aki_details[qty:].unlink()
            else:
                aki_details.unlink()

    @api.model_create_multi
    def create(self, vals_list):
        Spk = self.env["fleet.spk"]
        Product = self.env["product.product"]
        for vals in vals_list:
            if vals.get("spk_id") and not vals.get("analytic_account_id"):
                spk = Spk.browse(vals["spk_id"])
                aa = spk.vehicle_id.analytic_account_id
                if aa:
                    vals["analytic_account_id"] = aa.id
            product_id = vals.get("product_id")
            if product_id:
                product = Product.browse(product_id)
                autofill_vals = self._get_product_autofill_vals(product)
                for key, value in autofill_vals.items():
                    if key not in vals:
                        vals[key] = value

        records = super().create(vals_list)
        records._sync_detail_lines()
        return records

    def write(self, vals):
        Product = self.env["product.product"]
        if "product_id" in vals and vals.get("product_id"):
            product = Product.browse(vals["product_id"])
            autofill_vals = self._get_product_autofill_vals(product)
            for key, value in autofill_vals.items():
                vals.setdefault(key, value)

        result = super().write(vals)
        if {"product_id", "quantity", "spk_id"}.intersection(vals):
            self._sync_detail_lines()
        return result

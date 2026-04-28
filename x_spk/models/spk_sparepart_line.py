from odoo import models, fields, api


class SPKSparepartLine(models.Model):
    _name = "spk.sparepart.line"
    _description = "SPK Sparepart Line"

    spk_id = fields.Many2one(
        "fleet.spk",
        string="SPK",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.template",
        string="Product",
        required=True,
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
    
    description = fields.Text(string='Description')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    tax_ids = fields.Many2many('account.tax', string='Taxes')

    @api.depends("quantity", "unit_price", "tax_ids")
    def _compute_subtotal(self):
        for record in self:
            # Subtotal before tax
            subtotal_before_tax = record.quantity * record.unit_price
            record.subtotal_without_tax = subtotal_before_tax
            
            # Calculate total tax percentage from all applied taxes
            total_tax_rate = 0.0
            if record.tax_ids:
                for tax in record.tax_ids:
                    total_tax_rate += tax.amount / 100.0 if tax.amount_type == 'percent' else 0
            
            # Tax amount
            tax_amount = subtotal_before_tax * total_tax_rate
            record.tax_total = tax_amount
            
            # Subtotal with tax
            record.subtotal = subtotal_before_tax + tax_amount

    @api.model
    def _get_product_autofill_vals(self, product):
        return {
            "description": product.description_sale or product.display_name,
            "product_uom_id": product.uom_id.id,
            "unit_price": product.standard_price or product.list_price,
            "tax_ids": [(6, 0, product.supplier_taxes_id.ids)],
        }

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            product = line.product_id
            if not product:
                continue

            line.update(self._get_product_autofill_vals(product))

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
        for vals in vals_list:
            product_id = vals.get("product_id")
            if not product_id:
                continue
            product = self.env["product.template"].browse(product_id)
            autofill_vals = self._get_product_autofill_vals(product)
            for key, value in autofill_vals.items():
                if key not in vals:
                    vals[key] = value

        records = super().create(vals_list)
        records._sync_detail_lines()
        return records

    def write(self, vals):
        if "product_id" in vals and vals.get("product_id"):
            product = self.env["product.template"].browse(vals["product_id"])
            autofill_vals = self._get_product_autofill_vals(product)
            for key, value in autofill_vals.items():
                vals.setdefault(key, value)

        result = super().write(vals)
        if {"product_id", "quantity", "spk_id"}.intersection(vals):
            self._sync_detail_lines()
        return result

    def unlink(self):
        tyre_details = self.env["spk.tyre.line"].search([
            ("product_line_id", "in", self.ids),
        ])
        aki_details = self.env["spk.aki.line"].search([
            ("product_line_id", "in", self.ids),
        ])
        tyre_details.unlink()
        aki_details.unlink()
        return super().unlink()

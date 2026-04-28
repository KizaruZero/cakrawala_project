from odoo import models, fields, api


class SPKOnRiskProductLine(models.Model):
    _name = "spk.on.risk.product.line"
    _description = "SPK On Risk Product Line"

    spk_id = fields.Many2one(
        "fleet.spk",
        string="SPK",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        domain="[('is_on_risk', '=', True)]",
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
    description = fields.Char(
        string="Description",
    )
    subtotal = fields.Float(
        string="Subtotal",
        compute="_compute_subtotal",
        store=True,
    )

    @api.depends("quantity", "unit_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.description = line.product_id.display_name
                line.unit_price = getattr(line.product_id, "list_price", 0.0)

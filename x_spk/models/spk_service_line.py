from odoo import models, fields, api


class SPKServiceLine(models.Model):
    _name = "spk.service.line"
    _description = "SPK Service Line"

    spk_id = fields.Many2one(
        "fleet.spk",
        string="SPK",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Service",
        required=True,
        domain="[('type', '=', 'service')]",
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
        string="Subtotal",
        compute="_compute_subtotal",
    )

    @api.depends("quantity", "unit_price")
    def _compute_subtotal(self):
        for record in self:
            record.subtotal = record.quantity * record.unit_price

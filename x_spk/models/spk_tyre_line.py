from odoo import models, fields, api


class SPKTyreLine(models.Model):
    _name = "spk.tyre.line"
    _description = "SPK Tyre Detail Line"

    spk_id = fields.Many2one(
        "fleet.spk",
        string="SPK",
        required=True,
        ondelete="cascade",
    )
    product_line_id = fields.Many2one(
        "spk.sparepart.line",
        string="Sparepart Product",
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.template",
        string="Tyre Product",
        related="product_line_id.product_id",
        store=True,
    )
    product_description = fields.Text(
        string="Product Description",
        compute="_compute_product_description",
        store=True,
    )
    # serial_number = fields.Char(
    #     string="Serial Number",
    #     required=True,
    # )
    old_production_number = fields.Char(
        string="Old Production Number",
    )
    new_production_number = fields.Char(
        string="New Production Number",
    )
    notes = fields.Text(string="Notes")

    @api.depends(
        "product_id",
        "product_id.description_sale",
        "product_id.display_name",
    )
    def _compute_product_description(self):
        for line in self:
            if not line.product_id:
                line.product_description = False
                continue
            line.product_description = (
                line.product_id.description_sale or line.product_id.display_name
            )

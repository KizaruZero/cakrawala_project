from odoo import models, fields, api


class SPKAkiLine(models.Model):
    _name = "spk.aki.line"
    _description = "SPK AKI (Battery) Detail Line"

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
        string="AKI Product",
        related="product_line_id.product_id",
        store=True,
    )
    product_description = fields.Text(
        string="Product Description",
        compute="_compute_product_description",
        store=True,
    )
    old_AKI_code = fields.Char(
        string="Old AKI Code",
    )
    new_AKI_code = fields.Char(
        string="New AKI Code",
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
            description_sale = getattr(line.product_id, "description_sale", False)
            display_name = getattr(line.product_id, "display_name", False)
            line.product_description = (
                description_sale or display_name
            )

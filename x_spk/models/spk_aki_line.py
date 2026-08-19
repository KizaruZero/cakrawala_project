from odoo import models, fields, api


class SPKAkiLine(models.Model):
    _name = "spk.aki.line"
    _description = "SPK ACCU (Battery) Detail Line"

    spk_id = fields.Many2one(
        "fleet.spk",
        string="SPK",
        required=True,
        ondelete="cascade",
    )
    product_line_id = fields.Many2one(
        "spk.product.line",
        string="Product Line",
        readonly=True,
        ondelete="cascade",
        copy=False,
    )
    product_id = fields.Many2one(
        "product.product",
        string="ACCU Product",
        related="product_line_id.product_id",
        store=True,
    )
    product_description = fields.Text(
        string="Product Description",
        compute="_compute_product_description",
        store=True,
    )
    old_AKI_code = fields.Char(
        string="Old ACCU Code",
        copy=False,
    )
    new_AKI_code = fields.Char(
        string="New ACCU Code",
        copy=False,
    )
    notes = fields.Text(string="Notes", copy=False)

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

    @api.onchange('product_id')
    def _onchange_product_id_aki(self):
        """
        Autofill old_AKI_code saat product dipilih.

        Strategi:
        1. Kumpulkan semua aki lines di SPK ini yang punya product template sama.
        2. Ambil N terbaru new_AKI_code dari history (by product template),
           lalu assign satu-per-satu ke tiap line secara berurutan.
        3. Fallback ke AKI Reference jika history kosong.
        """
        for line in self:
            if not line.product_id or not line.spk_id.vehicle_id:
                continue
            vehicle = line.spk_id.vehicle_id
            product = line.product_id

            same_product_lines = line.spk_id.aki_detail_ids.filtered(
                lambda l: l.product_id and l.product_id.product_tmpl_id == product.product_tmpl_id
            ).sorted('id')

            line_index = list(same_product_lines).index(line) if line in same_product_lines else 0

            latest_codes = vehicle._get_latest_aki_codes(product, limit=len(same_product_lines) + 1)
            
            if latest_codes and line_index < len(latest_codes):
                line.old_AKI_code = latest_codes[line_index]
            else:
                line.old_AKI_code = False


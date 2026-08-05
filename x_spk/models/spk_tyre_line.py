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
        "spk.product.line",
        string="Product Line",
        readonly=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
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

    @api.onchange('product_id')
    def _onchange_product_id_tyre(self):
        """
        Autofill old_production_number saat product dipilih.

        Strategi:
        1. Kumpulkan semua tyre lines di SPK ini yang punya product template sama.
        2. Ambil N terbaru new_production_number dari history (by product template),
           lalu assign satu-per-satu ke tiap line secara berurutan (terbaru ke yang paling baru juga).
        3. Fallback ke Tyre Reference jika history kosong (juga ambil sesuai jumlah line).
        """
        for line in self:
            if not line.product_id or not line.spk_id.vehicle_id:
                continue
            vehicle = line.spk_id.vehicle_id
            product = line.product_id

            # Kumpulkan semua tyre lines di SPK ini dengan product template yang sama,
            # urutkan by id supaya konsisten
            same_product_lines = line.spk_id.tyre_detail_ids.filtered(
                lambda l: l.product_id and l.product_id.product_tmpl_id == product.product_tmpl_id
            ).sorted('id')

            line_index = list(same_product_lines).index(line) if line in same_product_lines else 0

            # Gunakan helper dari fleet.vehicle yang sudah handle kombinasi History + Fallback Reference
            latest_numbers = vehicle._get_latest_tyre_numbers(product, limit=len(same_product_lines) + 1)
            
            if latest_numbers and line_index < len(latest_numbers):
                line.old_production_number = latest_numbers[line_index]
            elif latest_numbers:
                # Lebih banyak line dari jumlah total ban — pakai nomor terakhir sebagai fallback
                line.old_production_number = latest_numbers[-1]



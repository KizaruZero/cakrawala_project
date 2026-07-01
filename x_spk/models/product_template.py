from odoo import api, fields, models
from odoo.fields import Domain


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_tyre = fields.Boolean(
        string="Is Tyre",
        default=False,
        help="Check this if the product is a tyre for automatic SPK detail generation"
    )
    is_aki = fields.Boolean(
        string="Is ACCU (Battery)",
        default=False,
        help="Check this if the product is a battery (ACCU) for automatic SPK detail generation"
    )
    is_on_risk = fields.Boolean(
        string="Own Risk?",
        default=False,
        help="Check this if the product is own risk because accident"
    )
    spk_category = fields.Selection(
        [
            ("internal", "Internal"),
            ("external", "External"),
        ],
        string="SPK Category",
        help="Kategori SPK untuk menentukan tipe spare part atau service yang cocok"
    )
    kode_sparepart = fields.Char(string="Kode Sparepart")
    kategori_pekerjaan_id = fields.Many2one(
        "spk.kategori.pekerjaan",
        string="Kategori Pekerjaan",
    )
    kategori_sparepart_id = fields.Many2one(
        "spk.kategori.sparepart",
        string="Kategori Sparepart",
    )


class ProductProduct(models.Model):
    """Variant — baris SPK memilih product.product; filter _search pakai spk_category di template."""

    _inherit = "product.product"

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        cat = self.env.context.get("spk_filter_category")
        if cat in ("internal", "external"):
            # Own Risk products tidak dibatasi oleh spk_category;
            # produk biasa (non-own-risk) tetap difilter sesuai kategori.
            extra = Domain([
                "|",
                ("product_tmpl_id.is_on_risk", "=", True),
                ("product_tmpl_id.spk_category", "=", cat),
            ])
            domain = Domain(domain) & extra
        return super()._search(
            domain,
            offset=offset,
            limit=limit,
            order=order,
            active_test=active_test,
            bypass_access=bypass_access,
        )

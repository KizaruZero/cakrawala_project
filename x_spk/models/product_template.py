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
        string="On Risk?",
        default=False,
        help="Check this if the product is on risk because accident"
    )
    spk_category = fields.Selection(
        [
            ("internal", "Internal"),
            ("external", "External"),
        ],
        string="SPK Category",
        help="Kategori SPK untuk menentukan tipe spare part atau service yang cocok"
    )

class ProductProduct(models.Model):
    """Variant — baris SPK memilih product.product; filter _search pakai spk_category di template."""

    _inherit = "product.product"

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        cat = self.env.context.get("spk_filter_category")
        if cat in ("internal", "external"):
            extra = Domain([("product_tmpl_id.spk_category", "=", cat)])
            domain = Domain(domain) & extra
        return super()._search(
            domain,
            offset=offset,
            limit=limit,
            order=order,
            active_test=active_test,
            bypass_access=bypass_access,
        )

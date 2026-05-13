from odoo import models, fields


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

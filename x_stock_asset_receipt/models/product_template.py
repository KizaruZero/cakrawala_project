from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_vehicle = fields.Boolean(
        string='Is Vehicle',
        default=False,
        help="If enabled, Initial License Plate, Chassis Number, and Engine Number "
             "will be mandatory when receiving this product in a Goods Receipt."
    )

from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Remove the 'combo' option completely
    type = fields.Selection([
        ('consu', 'Goods'),
        ('service', 'Service')
    ], ondelete={'combo': 'set default'})

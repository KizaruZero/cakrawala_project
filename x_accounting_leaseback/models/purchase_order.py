from odoo import models, fields

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    asset_id = fields.Many2one('account.asset', string="Asset Link")

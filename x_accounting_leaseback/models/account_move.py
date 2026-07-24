from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    asset_id = fields.Many2one('account.asset', string="Asset Link")

from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    bastk_id = fields.Many2one('bastk.management', string='BASTK', copy=False)

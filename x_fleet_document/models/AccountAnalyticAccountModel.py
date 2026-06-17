from odoo import models, fields

class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    asset_number = fields.Char(string="Asset Number")
    license_plate = fields.Char(string="License Plate")
    company_id = fields.Many2one('res.company', string="Company")
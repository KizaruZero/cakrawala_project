from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    code = fields.Char(string='Company Code', help="Short code for the company, used in sequence generation (e.g. CSR)")

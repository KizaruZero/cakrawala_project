from odoo import models, fields

class BastkType(models.Model):
    _name = 'bastk.type'
    _description = 'BASTK Type'

    name = fields.Char(required=True)
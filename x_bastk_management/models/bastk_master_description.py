from odoo import models, fields

class BastkMasterDescription(models.Model):
    _name = 'bastk.master.description'
    _description = 'BASTK Master Description'

    name = fields.Char(required=True)
    type = fields.Selection([
        ('keluar', 'Keluar'),
        ('masuk', 'Masuk'),
        ('both', 'Both'),
    ], required=True, default='both')

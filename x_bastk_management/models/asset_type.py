from odoo import models, fields

class BastkAssetType(models.Model):
    _name = 'bastk.asset.type'
    _description = 'BASTK Asset Type'

    name = fields.Char(string='Name', required=True)

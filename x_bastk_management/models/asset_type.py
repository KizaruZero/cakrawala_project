from odoo import models, fields

class BastkAssetType(models.Model):
    _name = 'bastk.asset.type'
    _description = 'BASTK Asset Type'

    name = fields.Char(string='Name', required=True)
    photo_ids = fields.One2many('bastk.asset.type.image', 'asset_type_id', string='Photos')


class BastkAssetTypeImage(models.Model):
    _name = 'bastk.asset.type.image'
    _description = 'BASTK Asset Type Image'

    name = fields.Char(string='Name', required=True)
    asset_type_id = fields.Many2one('bastk.asset.type', string='Asset Type', required=True, ondelete='cascade')
    image = fields.Image(string='Image', max_width=1920, max_height=1920)
    annotated_image = fields.Image(string='Annotated Image', max_width=1920, max_height=1920)

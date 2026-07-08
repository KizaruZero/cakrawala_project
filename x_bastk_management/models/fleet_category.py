from odoo import models, fields

class FleetVehicleModelCategory(models.Model):
    _inherit = 'fleet.vehicle.model.category'

    photo_ids = fields.One2many('fleet.category.image', 'category_id', string='Photos')

class FleetCategoryImage(models.Model):
    _name = 'fleet.category.image'
    _description = 'Fleet Category Image'

    name = fields.Char(string='Name', required=True)
    category_id = fields.Many2one('fleet.vehicle.model.category', string='Category', required=True, ondelete='cascade')
    image = fields.Image(string='Image', max_width=1920, max_height=1920)

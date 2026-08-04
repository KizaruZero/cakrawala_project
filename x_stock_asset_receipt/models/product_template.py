from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_vehicle = fields.Boolean(
        string='Is Fleet',
        default=False,
        help="If enabled, Initial License Plate, Chassis Number, and Engine Number "
             "will be mandatory when receiving this product in a Goods Receipt. "
             "Tracking will automatically be set to By Unique Serial Number."
    )

    @api.onchange('is_vehicle')
    def _onchange_is_vehicle(self):
        for rec in self:
            if rec.is_vehicle:
                rec.is_storable = True
                rec.tracking = 'serial'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_vehicle'):
                vals['is_storable'] = True
                vals['tracking'] = 'serial'
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('is_vehicle'):
            vals['is_storable'] = True
            vals['tracking'] = 'serial'
        return super().write(vals)

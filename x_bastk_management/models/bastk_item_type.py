from odoo import models, fields, api


class BastkItemType(models.Model):
    _name = 'bastk.item.type'
    _description = 'BASTK Item Category'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    code = fields.Char(string='Code', index=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code') and vals.get('name'):
                name_val = vals['name']
                if isinstance(name_val, dict):
                    name_val = name_val.get('en_US') or next(iter(name_val.values()), '')
                vals['code'] = (name_val or '').strip().lower().replace(' ', '_')
        return super().create(vals_list)

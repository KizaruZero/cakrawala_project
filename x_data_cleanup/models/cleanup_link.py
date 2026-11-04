from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from . import cleanup_preset as preset

ACTIONS = [
    ('delete', 'Hapus record ini bila yang dirujuk dihapus (turunan)'),
    ('pull', 'Ikut hapus record yang dirujuk bila record ini dihapus'),
    ('both', 'Satu dokumen: hapus bersama ke dua arah'),
    ('nullify', 'Hanya kosongkan referensinya'),
]


class CleanupLink(models.Model):
    """ A relation rule: what the foreign key alone does not say about two documents """
    _name = 'x.cleanup.link'
    _description = 'Data Cleanup: Aturan Relasi'
    _order = 'model_name, field_name'

    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade')
    model_name = fields.Char(related='model_id.model', string='Nama Teknis', store=True)
    field_id = fields.Many2one(
        'ir.model.fields', string='Field', required=True, ondelete='cascade',
        domain="[('model_id', '=', model_id), ('ttype', 'in', ('many2one', 'many2many')), ('store', '=', True)]")
    field_name = fields.Char(related='field_id.name', string='Nama Field', store=True)
    relation = fields.Char(related='field_id.relation', string='Model Tujuan')
    ttype = fields.Selection(related='field_id.ttype', string='Tipe')
    action = fields.Selection(ACTIONS, string='Aturan', required=True, default='delete')
    active = fields.Boolean(default=True)
    note = fields.Char(string='Catatan')

    _field_unique = models.Constraint('UNIQUE(field_id)', 'Satu field hanya boleh punya satu aturan.')

    @api.constrains('field_id', 'action')
    def _check_action(self):
        for link in self:
            if link.ttype == 'many2many' and link.action not in ('delete', 'nullify'):
                raise ValidationError(_('Field many2many hanya bisa memakai aturan "Hapus" atau "Kosongkan".'))

    def _rule_maps(self):
        """ The rules keyed by table and column, as the engine reads them """
        m2o, m2m = {}, {}
        for link in self:
            if link.model_name not in self.env:
                continue
            model = self.env[link.model_name]
            field = model._fields.get(link.field_name)
            if not field or not field.store:
                continue
            if field.type == 'many2one':
                m2o[(model._table, field.name)] = link.action
            elif field.type == 'many2many' and link.action == 'delete':
                # the other side (comodel) is deleted -> delete this model's rows
                m2m[(field.relation, field.column2)] = (field.column1,)
        return {'m2o': m2o, 'm2m': m2m}

    @api.model
    def action_load_preset(self):
        existing = set(self.with_context(active_test=False).search([]).mapped('field_id').ids)
        vals_list = []
        for model_name, field_name, action in preset.LINKS:
            if model_name not in self.env:
                continue
            field = self.env[model_name]._fields.get(field_name)
            if not field or not field.store or field.type not in ('many2one', 'many2many'):
                continue
            ir_field = self.env['ir.model.fields'].sudo()._get(model_name, field_name)
            if not ir_field or ir_field.id in existing:
                continue
            vals_list.append({'model_id': ir_field.model_id.id, 'field_id': ir_field.id, 'action': action})
            existing.add(ir_field.id)
        self.create(vals_list)
        return True

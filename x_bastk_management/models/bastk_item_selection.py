from odoo import models, fields, api
from odoo.exceptions import ValidationError


class BastkItemSelection(models.Model):
    _name = 'bastk.item.selection'
    _description = 'BASTK Item Selection'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)

    @api.model
    def name_create(self, name):
        """Reuse existing selection if found (case-insensitive), otherwise create new."""
        cleaned_name = (name or '').strip()
        if cleaned_name:
            # Search case-insensitively without active/lang filter to reuse existing
            existing = self.with_context(active_test=False, lang=False).search([
                ('name', '=ilike', cleaned_name),
            ], limit=1)
            if not existing:
                existing = self.with_context(active_test=False).search([
                    ('name', '=ilike', cleaned_name),
                ], limit=1)
            if existing:
                if not existing.active:
                    existing.active = True
                return existing.id, existing.display_name
        return super().name_create(cleaned_name)

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for vals in vals_list:
            raw_name = vals.get('name')
            if isinstance(raw_name, dict):
                cleaned_name = next((v.strip() for v in raw_name.values() if isinstance(v, str) and v.strip()), '')
            elif isinstance(raw_name, str):
                cleaned_name = raw_name.strip()
                vals['name'] = cleaned_name
            else:
                cleaned_name = ''

            if cleaned_name:
                existing = self.with_context(active_test=False, lang=False).search([
                    ('name', '=ilike', cleaned_name),
                ], limit=1)
                if not existing:
                    existing = self.with_context(active_test=False).search([
                        ('name', '=ilike', cleaned_name),
                    ], limit=1)
                if existing:
                    if not existing.active and vals.get('active', True):
                        existing.active = True
                    records |= existing
                    continue

            records |= super().create([vals])
        return records

    @api.constrains('name')
    def _check_unique_name(self):
        for rec in self:
            cleaned = (rec.name or '').strip().lower()
            if not cleaned:
                continue
            duplicates = self.with_context(active_test=False, lang=False).search([
                ('id', '!=', rec.id),
                ('name', '=ilike', cleaned),
            ])
            if duplicates:
                raise ValidationError(f"Selection '{rec.name}' sudah ada. Silakan pilih opsi yang sudah tersedia.")

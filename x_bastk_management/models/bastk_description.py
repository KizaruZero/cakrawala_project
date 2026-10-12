from odoo import models, fields, api, Command
from odoo.exceptions import ValidationError


class BastkDescription(models.Model):
    _name = 'bastk.description'
    _description = 'BASTK Description'
    _order = 'sequence, id'

    bastk_id = fields.Many2one('bastk.management', required=True, ondelete='cascade')
    checklist_id = fields.Many2one('bastk.master.description', required=False)
    bastk_type = fields.Selection([
        ('keluar', 'Keluar'),
        ('masuk', 'Masuk'),
    ], required=True)

    sequence = fields.Integer(string='Sequence', default=10)
    display_type = fields.Selection([
        ('line_section', "Section"),
    ], default=False, help="Technical field for UX purpose.")
    name = fields.Char(string='Name / Description')

    item_type_id = fields.Many2one(
        'bastk.item.type',
        string='BASTK Item Category',
        compute='_compute_item_type_id',
        store=True,
        readonly=False,
    )
    item_type_code = fields.Char(
        string='BASTK Item Category Code',
        compute='_compute_item_type_code',
        store=True,
        index=True,
    )

    checklist_selection_ids = fields.Many2many(
        'bastk.item.selection',
        related='checklist_id.selection_ids',
        string='Allowed Selections',
        readonly=True,
    )
    selection_id = fields.Many2one(
        'bastk.item.selection',
        string='Selection',
        domain="[('id', 'in', checklist_selection_ids)]",
    )

    condition_baik = fields.Boolean(string='Baik')
    condition_tidak_ada = fields.Boolean(string='Tidak Ada')
    condition_rusak = fields.Boolean(string='Rusak')
    condition_hilang = fields.Boolean(string='Hilang')

    condition = fields.Selection([
        ('baik', 'Baik'),
        ('tidak_ada', 'Tidak Ada'),
        ('rusak', 'Rusak'),
        ('hilang', 'Hilang'),
    ], compute='_compute_condition', store=True)

    remarks = fields.Text()

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'sequence' in fields_list and not res.get('sequence'):
            bastk_id = self.env.context.get('default_bastk_id')
            bastk_type = self.env.context.get('default_bastk_type')
            if bastk_id:
                domain = [('bastk_id', '=', bastk_id)]
                if bastk_type:
                    domain.append(('bastk_type', '=', bastk_type))
                last_line = self.search(domain, order='sequence desc', limit=1)
                res['sequence'] = (last_line.sequence + 10) if last_line else 10
            else:
                res['sequence'] = 1000
        return res

    @api.depends('checklist_id', 'checklist_id.item_type_id')
    def _compute_item_type_id(self):
        for rec in self:
            if rec.display_type == 'line_section':
                continue
            if rec.checklist_id and rec.checklist_id.item_type_id:
                rec.item_type_id = rec.checklist_id.item_type_id
            elif not rec.item_type_id:
                rec.item_type_id = False

    @api.depends('item_type_id.code')
    def _compute_item_type_code(self):
        for rec in self:
            rec.item_type_code = rec.item_type_id.code or False

    @api.depends('selection_id', 'condition_baik', 'condition_tidak_ada', 'condition_rusak', 'condition_hilang')
    def _compute_condition(self):
        for rec in self:
            if rec.selection_id:
                s_name = (rec.selection_id.name or '').strip().lower()
                if 'baik' in s_name:
                    rec.condition = 'baik'
                elif 'tidak' in s_name or 'tidak ada' in s_name:
                    rec.condition = 'tidak_ada'
                elif 'rusak' in s_name:
                    rec.condition = 'rusak'
                elif 'hilang' in s_name:
                    rec.condition = 'hilang'
                else:
                    rec.condition = False
            elif rec.condition_baik:
                rec.condition = 'baik'
            elif rec.condition_tidak_ada:
                rec.condition = 'tidak_ada'
            elif rec.condition_rusak:
                rec.condition = 'rusak'
            elif rec.condition_hilang:
                rec.condition = 'hilang'
            else:
                rec.condition = False

    def _sync_selection_to_master(self):
        """Auto-add selection to master description if not mapped yet (only in draft/unsubmitted state)."""
        if self.env.context.get('skip_master_sync'):
            return
        for rec in self:
            if rec.display_type == 'line_section':
                continue
            # Guard against mutating master data from submitted/done/cancelled BASTKs
            if rec.bastk_id and rec.bastk_id.state not in ('draft', False):
                continue
            if rec.checklist_id and rec.selection_id:
                if rec.selection_id not in rec.checklist_id.selection_ids:
                    rec.checklist_id.sudo().write({
                        'selection_ids': [Command.link(rec.selection_id.id)],
                    })

    @api.onchange('selection_id')
    def _onchange_selection_id(self):
        if self.selection_id:
            s_name = (self.selection_id.name or '').strip().lower()
            self.condition_baik = 'baik' in s_name
            self.condition_tidak_ada = ('tidak' in s_name or 'tidak ada' in s_name)
            self.condition_rusak = 'rusak' in s_name
            self.condition_hilang = 'hilang' in s_name

            if self.checklist_id and (not self.bastk_id or self.bastk_id.state in ('draft', False)):
                if self.selection_id not in self.checklist_id.selection_ids:
                    self.checklist_id.sudo().write({
                        'selection_ids': [Command.link(self.selection_id.id)],
                    })

    @api.onchange('condition_baik')
    def _onchange_condition_baik(self):
        if self.condition_baik:
            self.condition_tidak_ada = False
            self.condition_rusak = False
            self.condition_hilang = False

    @api.onchange('condition_tidak_ada')
    def _onchange_condition_tidak_ada(self):
        if self.condition_tidak_ada:
            self.condition_baik = False
            self.condition_rusak = False
            self.condition_hilang = False

    @api.onchange('condition_rusak')
    def _onchange_condition_rusak(self):
        if self.condition_rusak:
            self.condition_baik = False
            self.condition_tidak_ada = False
            self.condition_hilang = False

    @api.onchange('condition_hilang')
    def _onchange_condition_hilang(self):
        if self.condition_hilang:
            self.condition_baik = False
            self.condition_tidak_ada = False
            self.condition_rusak = False

    @api.constrains('display_type', 'checklist_id', 'selection_id', 'condition_baik', 'condition_tidak_ada', 'condition_rusak', 'condition_hilang')
    def _check_single_condition(self):
        for rec in self:
            if rec.display_type == 'line_section':
                if rec.checklist_id or rec.selection_id or any([rec.condition_baik, rec.condition_tidak_ada, rec.condition_rusak, rec.condition_hilang]):
                    raise ValidationError("Section header tidak boleh memiliki checklist item atau pilihan kondisi.")
                continue

            count = sum([bool(rec.condition_baik), bool(rec.condition_tidak_ada), bool(rec.condition_rusak), bool(rec.condition_hilang)])
            if count > 1:
                raise ValidationError("Hanya diperbolehkan memilih 1 pilihan kondisi pada setiap line.")

            # If both selection_id and legacy boolean are set, ensure consistency
            if rec.selection_id and count == 1 and rec.condition:
                bool_map = {
                    'baik': rec.condition_baik,
                    'tidak_ada': rec.condition_tidak_ada,
                    'rusak': rec.condition_rusak,
                    'hilang': rec.condition_hilang,
                }
                if not bool_map.get(rec.condition):
                    raise ValidationError("Pilihan selection dan boolean kondisi tidak konsisten.")

            is_marked = bool(rec.selection_id) or (count == 1)
            if not is_marked and rec.bastk_id:
                if rec.bastk_type == 'keluar' and rec.bastk_id.state in ('submitted_outside', 'submitted_inside', 'done') and rec.bastk_id.need_submit_out:
                    raise ValidationError("Terdapat Item BASTK yang belum ditandai")
                elif rec.bastk_type == 'masuk' and rec.bastk_id.state in ('submitted_inside', 'done') and rec.bastk_id.need_submit_in and not (rec.bastk_id.is_disposal or rec.bastk_id.is_disabled_after_submitted_in):
                    raise ValidationError("Terdapat Item BASTK yang belum ditandai")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('display_type') == 'line_section':
                vals['checklist_id'] = False
                vals['selection_id'] = False
                vals['condition_baik'] = False
                vals['condition_tidak_ada'] = False
                vals['condition_rusak'] = False
                vals['condition_hilang'] = False
        records = super().create(vals_list)
        records._sync_selection_to_master()
        return records

    def write(self, vals):
        if vals.get('display_type') == 'line_section':
            vals.update({
                'checklist_id': False,
                'selection_id': False,
                'condition_baik': False,
                'condition_tidak_ada': False,
                'condition_rusak': False,
                'condition_hilang': False,
            })
        res = super().write(vals)
        if 'selection_id' in vals or 'checklist_id' in vals:
            self._sync_selection_to_master()
        return res

    @api.model
    def _ensure_bastk_section_headers(self):
        """Pastikan setiap BASTK yang memiliki checklist memiliki baris section header per kategori (Opsi 2A)."""
        item_types = self.env['bastk.item.type'].search([], order='sequence, id')
        if not item_types:
            return

        bastks_with_sections = self.search([('display_type', '=', 'line_section')]).mapped('bastk_id')
        all_bastks = self.search([('bastk_id', '!=', False)]).mapped('bastk_id')
        target_bastks = all_bastks - bastks_with_sections
        if not target_bastks:
            return

        for bastk in target_bastks:
            for b_type in ('keluar', 'masuk'):
                seq = 10
                for itype in item_types:
                    lines = self.search([
                        ('bastk_id', '=', bastk.id),
                        ('bastk_type', '=', b_type),
                        ('item_type_id', '=', itype.id),
                        ('display_type', '=', False),
                    ], order='id')
                    if lines:
                        self.create({
                            'bastk_id': bastk.id,
                            'bastk_type': b_type,
                            'display_type': 'line_section',
                            'name': itype.name,
                            'item_type_id': itype.id,
                            'sequence': seq,
                        })
                        seq += 1
                        for line in lines:
                            line.sequence = seq
                            seq += 1

                untyped_lines = self.search([
                    ('bastk_id', '=', bastk.id),
                    ('bastk_type', '=', b_type),
                    ('item_type_id', '=', False),
                    ('display_type', '=', False),
                ], order='id')
                if untyped_lines:
                    self.create({
                        'bastk_id': bastk.id,
                        'bastk_type': b_type,
                        'display_type': 'line_section',
                        'name': 'Lainnya',
                        'sequence': seq,
                    })
                    seq += 1
                    for line in untyped_lines:
                        line.sequence = seq
                        seq += 1

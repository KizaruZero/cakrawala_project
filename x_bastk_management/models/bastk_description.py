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

    @api.depends('checklist_id', 'checklist_id.item_type_id')
    def _compute_item_type_id(self):
        for rec in self:
            if rec.checklist_id and rec.checklist_id.item_type_id:
                rec.item_type_id = rec.checklist_id.item_type_id
            elif not rec.item_type_id:
                rec.item_type_id = False

    @api.depends('item_type_id', 'item_type_id.code', 'item_type_id.name', 'checklist_id', 'checklist_id.item_type_id')
    def _compute_item_type_code(self):
        for rec in self:
            itype = rec.item_type_id or (rec.checklist_id and rec.checklist_id.item_type_id)
            code = itype.code if itype else False
            if not code and itype and itype.name:
                name = itype.name.lower()
                if 'luar' in name or 'eksternal' in name:
                    code = 'bagian_luar'
                elif 'dalam' in name or 'internal' in name:
                    code = 'bagian_dalam'
                elif 'mesin' in name:
                    code = 'bagian_mesin'
                else:
                    code = name.strip().lower().replace(' ', '_')
            if code in ('internal', 'bagian_dalam'):
                code = 'bagian_dalam'
            elif code in ('eksternal', 'bagian_luar'):
                code = 'bagian_luar'
            elif code in ('mesin', 'bagian_mesin'):
                code = 'bagian_mesin'
            rec.item_type_code = code or False

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
        """Auto-add selection to master description if not mapped yet."""
        for rec in self:
            if rec.checklist_id and rec.selection_id:
                if rec.selection_id not in rec.checklist_id.selection_ids:
                    rec.checklist_id.sudo().write({
                        'selection_ids': [Command.link(rec.selection_id.id)],
                    })

    @api.onchange('selection_id')
    def _onchange_selection_id(self):
        if self.selection_id and self.checklist_id:
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

    @api.constrains('selection_id', 'display_type', 'condition_baik', 'condition_tidak_ada', 'condition_rusak', 'condition_hilang')
    def _check_single_condition(self):
        for rec in self:
            if rec.display_type == 'line_section':
                continue
            count = sum([bool(rec.condition_baik), bool(rec.condition_tidak_ada), bool(rec.condition_rusak), bool(rec.condition_hilang)])
            if count > 1:
                raise ValidationError("Hanya diperbolehkan memilih 1 pilihan kondisi pada setiap line.")
            is_marked = bool(rec.selection_id) or (count == 1)
            if not is_marked and rec.bastk_id:
                if rec.bastk_type == 'keluar' and rec.bastk_id.state in ('submitted_outside', 'submitted_inside', 'done') and rec.bastk_id.need_submit_out:
                    raise ValidationError("Terdapat Item BASTK yang belum ditandai")
                elif rec.bastk_type == 'masuk' and rec.bastk_id.state in ('submitted_inside', 'done') and rec.bastk_id.need_submit_in and not (rec.bastk_id.is_disposal or rec.bastk_id.is_disabled_after_submitted_in):
                    raise ValidationError("Terdapat Item BASTK yang belum ditandai")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_selection_to_master()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'selection_id' in vals or 'checklist_id' in vals:
            self._sync_selection_to_master()
        return res

    def init(self):
        super().init()
        self._ensure_bastk_section_headers()

    @api.model
    def _ensure_bastk_section_headers(self):
        """Pastikan setiap BASTK yang memiliki checklist memiliki baris section header per kategori (Opsi 2A)."""
        bastks_with_sections = self.search([('display_type', '=', 'line_section')]).mapped('bastk_id')
        all_bastks = self.search([('bastk_id', '!=', False)]).mapped('bastk_id')
        target_bastks = all_bastks - bastks_with_sections
        if not target_bastks:
            return

        item_types = self.env['bastk.item.type'].search([], order='sequence, id')

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




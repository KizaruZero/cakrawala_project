import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

from . import cleanup_preset as preset
from .cleanup_engine import FRAMEWORK_PREFIXES, PROTECTED_PREFIX

_logger = logging.getLogger(__name__)

CATEGORIES = [
    ('transaction', 'Transaksi (boleh dihapus)'),
    ('master', 'Master / Konfigurasi (dilindungi)'),
    ('review', 'Perlu Review (dilindungi)'),
]


class CleanupTarget(models.Model):
    """ The classification of a model: what a cleanup may delete """
    _name = 'x.cleanup.target'
    _description = 'Data Cleanup: Klasifikasi Model'
    _order = 'area, sequence, is_root desc, model_name'
    _rec_name = 'name'

    name = fields.Char(string='Nama', required=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade', index=True)
    model_name = fields.Char(related='model_id.model', string='Nama Teknis', store=True, index=True)
    area = fields.Selection(preset.AREAS, string='Area', required=True, default='other')
    category = fields.Selection(CATEGORIES, string='Klasifikasi', required=True, default='review')
    is_root = fields.Boolean(
        string='Dokumen Utama',
        help='Dokumen yang dipakai user (SO, PO, invoice, picking, ...): mendapat menu Action > Data Cleanup '
             'dan dilaporkan bila ikut terhapus dari pilihan lain.')
    domain = fields.Char(
        string='Filter', default='[]',
        help='Batas record yang dihapus saat "Hapus Semua" (misal model asset tidak ikut: '
             '[("state", "!=", "model")]).')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    note = fields.Text(string='Catatan')
    record_count = fields.Integer(string='Jumlah Record', compute='_compute_record_count')
    has_active_field = fields.Boolean(compute='_compute_record_count')
    action_delete_id = fields.Many2one('ir.actions.server', string='Action Hapus', ondelete='set null', readonly=True)
    action_archive_id = fields.Many2one('ir.actions.server', string='Action Arsip', ondelete='set null', readonly=True)

    _model_unique = models.Constraint('UNIQUE(model_id)', 'Satu model hanya boleh diklasifikasi sekali.')

    @api.depends('model_name', 'domain')
    def _compute_record_count(self):
        for target in self:
            count, has_active = 0, False
            if target.model_name in self.env:
                model = self.env[target.model_name]
                has_active = 'active' in model._fields
                try:
                    count = model.sudo().with_context(active_test=False).search_count(target._get_domain())
                except Exception:  # noqa: BLE001 - a broken filter shows 0, not an error page
                    count = 0
            target.record_count = count
            target.has_active_field = has_active

    def _get_domain(self):
        self.ensure_one()
        try:
            domain = safe_eval(self.domain or '[]')
        except Exception as e:
            raise UserError(_('Filter pada %(name)s tidak valid: %(error)s', name=self.name, error=e)) from e
        return domain

    # ------------------------------------------------------------------
    # Action menu entries on the cleaned models
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        targets = super().create(vals_list)
        targets._sync_actions()
        return targets

    def write(self, vals):
        res = super().write(vals)
        if {'category', 'is_root', 'active', 'model_id'} & set(vals):
            self._sync_actions()
        return res

    def unlink(self):
        (self.action_delete_id | self.action_archive_id).sudo().unlink()
        return super().unlink()

    def _sync_actions(self):
        Action = self.env['ir.actions.server'].sudo()
        group = self.env.ref('base.group_system')
        group_field = 'group_ids' if 'group_ids' in Action._fields else 'groups_id'
        for target in self:
            wanted = target.active and target.category == 'transaction' and target.is_root \
                and target.model_name in self.env
            if not wanted:
                (target.action_delete_id | target.action_archive_id).unlink()
                continue
            common = {
                'model_id': target.model_id.id,
                'binding_model_id': target.model_id.id,
                'binding_type': 'action',
                'binding_view_types': 'list,form',
                'state': 'code',
                group_field: [(6, 0, group.ids)],
            }
            if not target.action_delete_id:
                target.action_delete_id = Action.create(dict(
                    common, name=_('Data Cleanup: Hapus beserta turunan'),
                    code="action = env['x.cleanup.wizard'].action_open_for(model._name, records.ids)"))
            if 'active' in self.env[target.model_name]._fields:
                if not target.action_archive_id:
                    target.action_archive_id = Action.create(dict(
                        common, name=_('Data Cleanup: Arsipkan'),
                        code="action = env['x.cleanup.wizard'].action_archive_records(model._name, records.ids)"))
            elif target.action_archive_id:
                target.action_archive_id.unlink()

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def action_open_records(self):
        self.ensure_one()
        if self.model_name not in self.env:
            raise UserError(_('Model %s tidak terpasang.', self.model_name))
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': self.model_name,
            'view_mode': 'list,form',
            'domain': self._get_domain(),
            'context': {'active_test': False},
            'target': 'current',
        }

    def action_delete_all(self):
        self.ensure_one()
        return self.env['x.cleanup.wizard'].action_open_seed({self.model_name: 'all'}, mode='records',
                                                             title=_('Hapus semua %s', self.name))

    # ------------------------------------------------------------------
    # Preset and scan
    # ------------------------------------------------------------------
    @api.model
    def _model_record(self, name):
        return self.env['ir.model'].sudo().search([('model', '=', name)], limit=1)

    @api.model
    def action_load_preset(self):
        """ Classify the installed models of the preset; what is already classified is left as it is """
        existing = set(self.with_context(active_test=False).search([]).mapped('model_name'))
        vals_list = []
        for sequence, (name, area, is_root, domain) in enumerate(preset.TRANSACTIONS):
            ir_model = self._model_record(name)
            if name in existing or not ir_model or name not in self.env or not self.env[name]._auto:
                continue
            vals_list.append({'name': ir_model.name, 'model_id': ir_model.id, 'area': area,
                              'category': 'transaction', 'is_root': is_root, 'sequence': sequence,
                              'domain': repr(domain)})
            existing.add(name)
        for name, area in preset.MASTERS:
            ir_model = self._model_record(name)
            if name in existing or not ir_model or name not in self.env or not self.env[name]._auto:
                continue
            vals_list.append({'name': ir_model.name, 'model_id': ir_model.id, 'area': area,
                              'category': 'master', 'sequence': 100})
            existing.add(name)
        self.create(vals_list)
        self.env['x.cleanup.link'].action_load_preset()
        return True

    @api.model
    def action_scan_models(self):
        """ Add the models holding rows that nobody has classified yet, as To Review """
        existing = set(self.with_context(active_test=False).search([]).mapped('model_name'))
        vals_list = []
        for name in sorted(self.env.registry):
            model = self.env[name]
            if name in existing or model._abstract or model._transient or not model._auto:
                continue
            table = model._table
            if table.startswith(FRAMEWORK_PREFIXES) or table.startswith(PROTECTED_PREFIX):
                continue
            self.env.cr.execute("SELECT to_regclass(%s) IS NOT NULL", [table])
            if not self.env.cr.fetchone()[0]:
                continue
            self.env.cr.execute('SELECT EXISTS(SELECT 1 FROM "%s")' % table)
            if not self.env.cr.fetchone()[0]:
                continue
            ir_model = self._model_record(name)
            if ir_model:
                vals_list.append({'name': ir_model.name, 'model_id': ir_model.id, 'category': 'review',
                                  'area': 'other', 'sequence': 200})
                existing.add(name)
        self.create(vals_list)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'info', 'sticky': False,
                       'message': _('%s model baru ditambahkan sebagai "Perlu Review".', len(vals_list)),
                       'next': {'type': 'ir.actions.act_window_close'}},
        }

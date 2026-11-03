import json
import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.cleanup_engine import KIND_LABELS
from ..models.cleanup_preset import AREAS

_logger = logging.getLogger(__name__)


class CleanupWizard(models.TransientModel):
    _name = 'x.cleanup.wizard'
    _description = 'Data Cleanup: Hapus Data'

    title = fields.Char(readonly=True)
    state = fields.Selection([('draft', 'Opsi'), ('preview', 'Preview'), ('done', 'Selesai')], default='draft')
    mode = fields.Selection([('records', 'Record terpilih'), ('all', 'Semua transaksi')], default='records',
                            required=True)
    seed = fields.Text(readonly=True)
    seed_summary = fields.Char(string='Yang Dipilih', readonly=True)

    follow_links = fields.Boolean(
        string='Hapus beserta turunan', default=True,
        help='Ikut hapus dokumen turunan menurut Aturan Relasi (delivery & invoice dari SO, PO dari PR, ...). '
             'Bila mati (mode ketat), pembersihan ditolak kalau ada dokumen lain yang ikut terhapus.')
    follow_reconcile = fields.Boolean(
        string='Ikut hapus pembayaran yang terekonsiliasi', default=True,
        help='Pembayaran/jurnal yang direkonsiliasi dengan invoice yang dihapus ikut dihapus (satu tingkat).')
    adjust_quants = fields.Boolean(
        string='Sesuaikan stok on hand', default=True,
        help='Kembalikan efek move yang sudah selesai ke stok on hand dan lepas reservasinya. '
             'Tidak berlaku bila semua quant ikut dihapus.')
    clear_lock_dates = fields.Boolean(string='Kosongkan lock date akuntansi', default=True)
    reset_sequences = fields.Boolean(string='Reset sequence transaksi ke 1', default=True)
    reset_fleet = fields.Boolean(string='Reset status unit fleet', default=False)
    fleet_all = fields.Boolean(string='Semua unit fleet', default=True,
                               help='Bila mati, hanya unit yang terkait data yang dihapus.')
    fleet_state = fields.Selection(selection='_selection_fleet_states', string='Status Fleet Baru')
    fleet_substatus = fields.Selection(selection='_selection_fleet_substatus', string='Sub-status Fleet Baru')
    fleet_clear_customer = fields.Boolean(string='Kosongkan "Last Customer"', default=True)

    line_ids = fields.One2many('x.cleanup.wizard.line', 'wizard_id', string='Rencana')
    delete_line_ids = fields.One2many('x.cleanup.wizard.line', 'wizard_id', domain=[('action', '=', 'delete')])
    other_line_ids = fields.One2many('x.cleanup.wizard.line', 'wizard_id', domain=[('action', '!=', 'delete')])
    total_delete = fields.Integer(string='Total Dihapus', readonly=True)
    total_nullify = fields.Integer(string='Total Referensi Dikosongkan', readonly=True)
    warning_html = fields.Html(sanitize=False, readonly=True)
    blocked = fields.Boolean(readonly=True)
    simulation_ok = fields.Boolean(readonly=True)
    simulation_message = fields.Text(readonly=True)
    has_unclassified = fields.Boolean(readonly=True)
    accept_unclassified = fields.Boolean(string='Saya sudah mereview data yang belum diklasifikasi')
    database_name = fields.Char(compute='_compute_database_name')
    confirm_backup = fields.Boolean(string='Saya sudah mengambil backup database ini')
    confirm_dbname = fields.Char(string='Ketik nama database')
    result_html = fields.Html(sanitize=False, readonly=True)
    log_id = fields.Many2one('x.cleanup.log', readonly=True)

    def _compute_database_name(self):
        for wizard in self:
            wizard.database_name = self.env.cr.dbname

    @api.model
    def _selection_from_table(self, table):
        self.env.cr.execute("SELECT to_regclass(%s) IS NOT NULL", [table])
        if not self.env.cr.fetchone()[0]:
            return []
        model = {'fleet_vehicle_state': 'fleet.vehicle.state', 'vehicle_substatus': 'vehicle.substatus'}[table]
        if model not in self.env:
            return []
        records = self.env[model].sudo().with_context(active_test=False).search([])
        return [(str(r.id), r.display_name) for r in records]

    @api.model
    def _selection_fleet_states(self):
        return self._selection_from_table('fleet_vehicle_state')

    @api.model
    def _selection_fleet_substatus(self):
        return self._selection_from_table('vehicle_substatus')

    # ------------------------------------------------------------------
    # Opening
    # ------------------------------------------------------------------
    @api.model
    def action_open_seed(self, seed, mode='records', title=False):
        self.env['x.cleanup.guard'].check_admin()
        engine = self.env['x.cleanup.engine']
        summary = []
        for model_name, ids in seed.items():
            label = self.env[model_name]._description if model_name in self.env else model_name
            summary.append('%s: %s' % (label, _('semua') if ids == 'all' else len(ids)))
        wizard = self.create({
            'mode': mode,
            'seed': engine.seed_dumps(seed),
            'seed_summary': '; '.join(summary)[:500],
            'title': title or _('Hapus Data'),
            'adjust_quants': mode == 'records',
            'clear_lock_dates': mode == 'all',
            'reset_sequences': mode == 'all',
        })
        return wizard._reopen()

    @api.model
    def action_open_for(self, model_name, ids):
        if not ids:
            raise UserError(_('Pilih minimal satu record.'))
        return self.action_open_seed({model_name: ids}, title=_('Hapus %s record beserta turunannya', len(ids)))

    @api.model
    def action_open_all(self):
        targets = self.env['x.cleanup.target'].sudo().search([('category', '=', 'transaction')])
        seed = {t.model_name: 'all' for t in targets if t.model_name in self.env}
        return self.action_open_seed(seed, mode='all', title=_('Hapus Semua Transaksi'))

    @api.model
    def action_archive_records(self, model_name, ids):
        self.env['x.cleanup.guard'].check_admin()
        records = self.env[model_name].with_context(active_test=False).browse(ids).exists()
        records.filtered('active').action_archive()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': _('%s record diarsipkan.', len(records)),
                       'next': {'type': 'ir.actions.act_window_close'}},
        }

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.title,
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------
    def _options(self):
        return {
            'follow_links': self.follow_links,
            'follow_reconcile': self.follow_reconcile,
            'adjust_quants': self.adjust_quants,
            'clear_lock_dates': self.mode == 'all' and self.clear_lock_dates,
            'reset_sequences': self.mode == 'all' and self.reset_sequences,
            'reset_fleet': self.reset_fleet,
            'fleet_all': self.fleet_all,
            'fleet_state_id': self.fleet_state,
            'fleet_substatus_id': self.fleet_substatus,
            'fleet_clear_customer': self.fleet_clear_customer,
        }

    def _plan(self):
        engine = self.env['x.cleanup.engine']
        return engine.compute_plan(engine.seed_loads(self.seed), self._options())

    def action_preview(self):
        self.ensure_one()
        self.env['x.cleanup.guard'].check_admin()
        engine = self.env['x.cleanup.engine']
        plan, data = self._plan()
        lines = engine.describe(plan, data)
        warnings = engine.warnings(plan, data)
        ok, message = (False, _('Simulasi tidak dijalankan karena ada penolakan di atas.'))
        if not plan.blockers and plan.total():
            ok, message = engine.simulate(plan, data, self._options())
        elif not plan.total():
            message = _('Tidak ada data yang akan dihapus.')
        self.line_ids.unlink()
        self.write({
            'state': 'preview',
            'line_ids': [fields.Command.create(line) for line in lines],
            'total_delete': plan.total(),
            'total_nullify': sum(len(rows) for rows in plan.nullify_rows.values()),
            'warning_html': self._warning_html(plan.blockers, warnings),
            'blocked': bool(plan.blockers) or not ok,
            'simulation_ok': ok,
            'simulation_message': message,
            'has_unclassified': bool(plan.unclassified),
            'accept_unclassified': False,
            'confirm_backup': False,
            'confirm_dbname': False,
        })
        return self._reopen()

    @api.model
    def _warning_html(self, blockers, warnings):
        items = [Markup('<div class="alert alert-danger mb-2" role="alert"><b>%s</b> %s</div>') % (_('Ditolak:'), b)
                 for b in blockers]
        for level, text in warnings:
            css = 'alert-warning' if level == 'warning' else 'alert-info'
            items.append(Markup('<div class="alert %s mb-2" role="alert">%s</div>') % (css, text))
        return Markup('').join(items) if items else False

    def action_back(self):
        self.ensure_one()
        self.line_ids.unlink()
        self.state = 'draft'
        return self._reopen()

    def action_execute(self):
        self.ensure_one()
        guard = self.env['x.cleanup.guard']
        guard.check_unlocked()
        if self.state != 'preview':
            raise UserError(_('Jalankan preview dulu.'))
        if self.blocked:
            raise UserError(_('Preview menunjukkan pembersihan ini ditolak. Perbaiki dulu penyebabnya.'))
        if not self.confirm_backup:
            raise UserError(_('Centang konfirmasi bahwa backup sudah diambil.'))
        if (self.confirm_dbname or '').strip() != self.env.cr.dbname:
            raise UserError(_('Ketik nama database "%s" persis untuk konfirmasi. Belum ada yang dihapus.',
                              self.env.cr.dbname))
        if self.has_unclassified and not self.accept_unclassified:
            raise UserError(_('Centang konfirmasi review data yang belum diklasifikasi.'))
        engine = self.env['x.cleanup.engine']
        # the plan is computed again: the data may have changed since the preview
        plan, data = self._plan()
        if plan.total() != self.total_delete:
            raise UserError(_(
                'Data berubah sejak preview (%(before)s menjadi %(now)s baris). Jalankan preview lagi.',
                before=self.total_delete, now=plan.total()))
        options = self._options()
        result = engine.execute(plan, data, options)
        deleted = sorted(result['deleted'].items(), key=lambda item: -item[1])
        details = '\n'.join('%s: %s' % (engine._table_label(data, table), count) for table, count in deleted)
        details += '\n\n' + '\n'.join('%s: %s dikosongkan' % (key, count)
                                      for key, count in result['nullified'].items())
        log = self.env['x.cleanup.log'].sudo().create({
            'name': '%s - %s' % (self.title, self.seed_summary or ''),
            'user_login': self.env.user.login,
            'database': self.env.cr.dbname,
            'mode': self.mode,
            'total_deleted': result['deleted_total'],
            'total_nullified': sum(result['nullified'].values()),
            'options': json.dumps(options, indent=1, default=str),
            'details': details,
            'post_notes': '\n'.join(result['post']),
        })
        _logger.warning('Data Cleanup by %s on %s: %s rows deleted (%s)', self.env.user.login,
                        self.env.cr.dbname, result['deleted_total'], self.seed_summary)
        notes = Markup('').join(Markup('<li>%s</li>') % note for note in result['post'])
        self.write({
            'state': 'done',
            'log_id': log.id,
            'result_html': Markup('<p><b>%s</b></p><ul>%s</ul>') % (
                _('%(rows)s baris dihapus, %(refs)s referensi dikosongkan.', rows=result['deleted_total'],
                  refs=sum(result['nullified'].values())), notes),
        })
        return self._reopen()

    def action_open_log(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'x.cleanup.log', 'res_id': self.log_id.id,
                'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current'}


class CleanupWizardLine(models.TransientModel):
    _name = 'x.cleanup.wizard.line'
    _description = 'Data Cleanup: Baris Rencana'
    _order = 'action, count desc, table_name'

    wizard_id = fields.Many2one('x.cleanup.wizard', required=True, ondelete='cascade')
    table_name = fields.Char(string='Tabel')
    model = fields.Char(string='Model')
    label = fields.Char(string='Data')
    area = fields.Selection(AREAS, string='Area')
    kind = fields.Selection(list(KIND_LABELS.items()), string='Klasifikasi')
    action = fields.Selection([('delete', 'Dihapus'), ('nullify', 'Referensi dikosongkan'),
                               ('relation', 'Relasi dihapus')], string='Tindakan')
    count = fields.Integer(string='Jumlah')
    seed_count = fields.Integer(string='Dipilih')
    reason = fields.Char(string='Alasan')

    def action_open_rows(self):
        """ The records of this line, before they are deleted """
        self.ensure_one()
        if not self.model or self.model not in self.env:
            raise UserError(_('Tabel ini tidak punya model untuk ditampilkan.'))
        wizard = self.wizard_id
        plan, _data = wizard._plan()
        ids = plan.delete.get(self.table_name) if self.action == 'delete' else set().union(*[
            rows for (table, _column), rows in plan.nullify_rows.items() if table == self.table_name] or [set()])
        return {
            'type': 'ir.actions.act_window',
            'name': self.label,
            'res_model': self.model,
            'view_mode': 'list,form',
            'domain': [('id', 'in', sorted(ids or []))],
            'context': {'active_test': False, 'create': False},
            'target': 'new',
        }

"""The cleanup engine.

1. The relations are read from the foreign keys of PostgreSQL, so every installed module, custom or not,
   is covered without being listed anywhere.
2. A *plan* is computed from a seed (the records chosen, or all the transactions): every row that has to go
   with them, every reference to empty, and what would be refused (master data that would be lost).
3. The plan is run in one transaction: references emptied, rows deleted table by table (a table refused
   by a foreign key is tried again once the others are gone, and a cycle of references is broken by
   emptying them), what is attached to the deleted documents removed, the records that point at them
   recomputed. Any failure undoes everything.
4. The preview runs the same plan inside a savepoint that is rolled back: what it reports is what the
   database really accepts.
"""
import json
import logging
from collections import defaultdict, deque

import psycopg2

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

# the tables of the framework: never seeded, never offered; their rows only go when the database itself
# cascades a deletion to them
FRAMEWORK_PREFIXES = (
    'ir_', 'res_users', 'res_groups', 'res_company', 'res_lang', 'res_currency', 'res_country', 'res_bank',
    'bus_', 'base_', 'web_', 'auth_', 'iap_', 'digest_', 'utm_', 'mail_', 'discuss_', 'rating_', 'sms_',
    'snailmail_', 'spreadsheet_', 'onboarding_', 'report_', 'html_', 'privacy_', 'fetchmail_', 'resource_',
    'decimal_precision', 'barcode_', 'phone_', 'portal_', 'calendar_alarm', 'res_device', 'res_role',
)
PROTECTED_PREFIX = 'x_cleanup_'
# the records attached to a document by its model name: (table, model column, id column)
LINKED_TABLES = [
    ('mail_message', 'model', 'res_id'),
    ('mail_followers', 'res_model', 'res_id'),
    ('mail_activity', 'res_model', 'res_id'),
    ('rating_rating', 'res_model', 'res_id'),
    ('ir_attachment', 'res_model', 'res_id'),
    ('ir_model_data', 'model', 'res_id'),
]
# editable computed fields that only follow the documents: recomputed on the kept records too
RECOMPUTE_EDITABLE = {
    'sale.order.line': {'qty_delivered'},
    'purchase.order.line': {'qty_received'},
}
MAX_PASSES = 15
SAMPLE = 10

KIND_LABELS = {
    'transaction': 'Transaksi',
    'master': 'Master / Konfigurasi',
    'review': 'Perlu Review',
    'unclassified': 'Belum Diklasifikasi',
    'framework': 'Framework',
    'transient': 'Wizard (transient)',
    'technical': 'Teknis',
    'relation': 'Relasi Many2many',
    'protected': 'Data Cleanup',
}
REASON_LABELS = {
    'seed': 'Dipilih',
    'child': 'Baris/anak dokumen',
    'link': 'Turunan (aturan relasi)',
    'pull': 'Dokumen induk/terkait',
    'header': 'Dokumen induk',
    'reconcile': 'Rekonsiliasi (pembayaran/lawan transaksi)',
    'db_cascade': 'Ikut terhapus oleh database (cascade)',
    'unclassified': 'Belum diklasifikasi, ikut terhapus',
    'technical': 'Data teknis/wizard',
}


class _DryRunRollback(Exception):
    """ Raised at the end of a simulation to roll its savepoint back """


class CleanupPlan:
    """ What a cleanup deletes, empties and refuses. Plain Python: it lives for one request. """

    def __init__(self):
        self.seed = defaultdict(set)          # table -> ids chosen
        self.delete = defaultdict(set)        # table -> ids to delete
        self.reasons = defaultdict(set)       # table -> reasons its rows are deleted for
        self.nullify = defaultdict(set)       # (table, column) -> deleted parent ids it references
        self.nullify_rows = defaultdict(set)  # (table, column) -> ids of the rows whose reference is emptied
        self.relation = defaultdict(set)      # (relation table, column) -> deleted ids it references
        self.unclassified = defaultdict(set)  # table -> ids deleted though not classified
        self.neighbours = defaultdict(set)    # table -> kept ids whose computed fields are recomputed
        self.reconcile_moves = set()          # moves pulled through a reconciliation
        self.blockers = []
        self.notes = []

    def total(self):
        return sum(len(ids) for ids in self.delete.values())


class CleanupEngine(models.AbstractModel):
    _name = 'x.cleanup.engine'
    _description = 'Data Cleanup Engine'

    # ------------------------------------------------------------------
    # Database structure
    # ------------------------------------------------------------------
    @api.model
    def _graph(self):
        """ The single-column foreign keys of the database, both ways, and the tables that have an id """
        cr = self.env.cr
        cr.execute("""
            SELECT cl.relname, a.attname, pcl.relname, c.confdeltype, a.attnotnull
              FROM pg_constraint c
              JOIN pg_class cl ON cl.oid = c.conrelid
              JOIN pg_class pcl ON pcl.oid = c.confrelid
              JOIN pg_namespace n ON n.oid = cl.relnamespace
              JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
              JOIN pg_attribute pa ON pa.attrelid = c.confrelid AND pa.attnum = c.confkey[1]
             WHERE c.contype = 'f' AND array_length(c.conkey, 1) = 1 AND pa.attname = 'id'
               AND n.nspname = current_schema()
        """)
        incoming, outgoing = defaultdict(list), defaultdict(list)
        for child, column, parent, deltype, notnull in cr.fetchall():
            fk = {'child': child, 'column': column, 'parent': parent, 'deltype': deltype, 'notnull': notnull}
            incoming[parent].append(fk)
            outgoing[child].append(fk)
        cr.execute("""
            SELECT table_name FROM information_schema.columns
             WHERE table_schema = current_schema() AND column_name = 'id'
        """)
        id_tables = {row[0] for row in cr.fetchall()}
        table_model, transient = {}, set()
        for name in self.env.registry:
            model = self.env[name]
            if model._abstract or not model._auto:
                continue
            if model._transient:
                transient.add(model._table)
                table_model.setdefault(model._table, name)
            elif model._table not in table_model or table_model[model._table] in transient:
                table_model[model._table] = name
        return {'incoming': incoming, 'outgoing': outgoing, 'id_tables': id_tables,
                'table_model': table_model, 'transient': transient}

    @api.model
    def _context_data(self):
        """ The structure, the classification and the relation rules, read once per plan """
        graph = self._graph()
        targets = self.env['x.cleanup.target'].sudo().search([])
        categories = {t.model_name: t.category for t in targets}
        roots = {t.model_name for t in targets if t.is_root and t.category == 'transaction'}
        rules = self.env['x.cleanup.link'].sudo().search([])._rule_maps()
        return dict(graph, categories=categories, roots=roots, rules=rules, kinds={})

    @api.model
    def _kind(self, data, table):
        kinds = data['kinds']
        if table in kinds:
            return kinds[table]
        model = data['table_model'].get(table)
        if table.startswith(PROTECTED_PREFIX):
            kind = 'protected'
        elif table not in data['id_tables']:
            kind = 'relation'
        elif table in data['transient'] and model and self.env[model]._transient:
            kind = 'transient'
        elif model and model in data['categories']:
            kind = data['categories'][model]
        elif table.startswith(FRAMEWORK_PREFIXES):
            kind = 'framework'
        elif model is None:
            kind = 'technical'
        else:
            kind = 'unclassified'
        kinds[table] = kind
        return kind

    @api.model
    def _fetch_ids(self, query):
        self.env.cr.execute(query)
        return {row[0] for row in self.env.cr.fetchall() if row[0]}

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------
    @api.model
    def _resolve_seed(self, seed):
        """ seed: {model name: [ids] or 'all'} -> {table: ids}. 'all' follows the domain of the target. """
        tables = defaultdict(set)
        targets = {t.model_name: t for t in self.env['x.cleanup.target'].sudo().search([])}
        for model_name, ids in seed.items():
            if model_name not in self.env:
                continue
            model = self.env[model_name]
            if ids == 'all':
                target = targets.get(model_name)
                domain = target._get_domain() if target else []
                if domain:
                    ids = model.sudo().with_context(active_test=False).search(domain).ids
                else:
                    ids = self._fetch_ids(SQL('SELECT id FROM %s', SQL.identifier(model._table)))
            tables[model._table] |= set(ids)
        return tables

    @api.model
    def compute_plan(self, seed, options=None):
        """ The plan of a cleanup. options: follow_links, follow_reconcile """
        options = dict({'follow_links': True, 'follow_reconcile': True}, **(options or {}))
        self.env.flush_all()
        data = self._context_data()
        plan = CleanupPlan()
        queue = deque()

        def add(table, ids, reason):
            ids = set(ids) - plan.delete[table]
            if not ids:
                return
            kind = self._kind(data, table)
            if kind in ('master', 'protected') or (kind == 'framework' and reason != 'db_cascade'):
                plan.blockers.append(_(
                    '%(count)s record %(label)s (%(kind)s) akan ikut terhapus (%(reason)s). '
                    'Master data dan konfigurasi tidak boleh terhapus.',
                    count=len(ids), label=self._table_label(data, table), kind=KIND_LABELS.get(kind, kind),
                    reason=REASON_LABELS.get(reason, reason)))
                return
            plan.delete[table] |= ids
            plan.reasons[table].add(reason)
            if kind in ('unclassified', 'review'):
                plan.unclassified[table] |= ids
            queue.append((table, ids))

        for table, ids in self._resolve_seed(seed).items():
            plan.seed[table] |= ids
            add(table, ids, 'seed')

        while queue:
            table, ids = queue.popleft()
            ids_list = list(ids)
            self._plan_incoming(data, plan, table, ids_list, add, options)
            self._plan_outgoing(data, plan, table, ids_list, add, options)
            if table == 'account_move_line' and options['follow_reconcile']:
                self._plan_reconcile(data, plan, ids_list, add)

        # a reference held by a row that is deleted anyway needs no emptying
        for (table, column), rows in list(plan.nullify_rows.items()):
            rows -= plan.delete.get(table, set())
            if not rows:
                del plan.nullify_rows[(table, column)]
                plan.nullify.pop((table, column), None)
        for table in list(plan.neighbours):
            plan.neighbours[table] -= plan.delete.get(table, set())
        if not options['follow_links']:
            self._check_strict(data, plan)
        return plan, data

    @api.model
    def _plan_incoming(self, data, plan, table, ids, add, options):
        """ The rows that point at the deleted rows of `table` """
        rules = data['rules']
        for fk in data['incoming'].get(table, []):
            child, column = fk['child'], fk['column']
            kind = self._kind(data, child)
            if kind == 'relation':
                self._plan_relation(data, plan, fk, ids, add, options)
                continue
            rows = self._fetch_ids(SQL('SELECT id FROM %s WHERE %s = ANY(%s)',
                                 SQL.identifier(child), SQL.identifier(column), ids))
            rows -= plan.delete.get(child, set())
            if not rows:
                continue
            rule = rules['m2o'].get((child, column)) if options['follow_links'] else None
            cascade, notnull = fk['deltype'] == 'c', fk['notnull']
            if kind == 'transaction':
                if rule in ('delete', 'both') or cascade or notnull:
                    add(child, rows, 'link' if rule in ('delete', 'both') and not (cascade or notnull) else 'child')
                else:
                    self._nullify(plan, fk, ids, rows, neighbour=True)
            elif kind in ('transient', 'technical'):
                if cascade or notnull:
                    add(child, rows, 'technical')
                else:
                    self._nullify(plan, fk, ids, rows)
            elif kind in ('unclassified', 'review'):
                if cascade or notnull:
                    add(child, rows, 'unclassified')
                else:
                    self._nullify(plan, fk, ids, rows)
            elif kind == 'framework':
                if cascade:
                    add(child, rows, 'db_cascade')
                elif notnull:
                    plan.blockers.append(self._blocker_text(data, fk, rows))
                else:
                    self._nullify(plan, fk, ids, rows)
            else:  # master, protected
                if cascade or notnull:
                    plan.blockers.append(self._blocker_text(data, fk, rows))
                else:
                    self._nullify(plan, fk, ids, rows)

    @api.model
    def _plan_relation(self, data, plan, fk, ids, add, options):
        """ A many2many table pointing at deleted rows: its rows go; a rule may take the other side along """
        rel, column = fk['child'], fk['column']
        plan.relation[(rel, column)] |= set(ids)
        others = [o for o in data['outgoing'].get(rel, []) if o['column'] != column]
        rule = data['rules']['m2m'].get((rel, column)) if options['follow_links'] else None
        for other in others:
            other_ids = self._fetch_ids(SQL('SELECT %s FROM %s WHERE %s = ANY(%s)', SQL.identifier(other['column']),
                                      SQL.identifier(rel), SQL.identifier(column), ids))
            if not other_ids:
                continue
            if rule and rule[0] == other['column']:
                add(other['parent'], other_ids, 'link')
            elif self._kind(data, other['parent']) == 'transaction':
                plan.neighbours[other['parent']] |= other_ids

    @api.model
    def _plan_outgoing(self, data, plan, table, ids, add, options):
        """ The documents the deleted rows of `table` belong to: their header, and the pull rules """
        if self._kind(data, table) != 'transaction':
            return
        rules = data['rules']
        fks = data['outgoing'].get(table, [])
        headers = [fk for fk in fks if fk['notnull'] and fk['deltype'] == 'c'
                   and fk['parent'] != table and self._kind(data, fk['parent']) == 'transaction']
        for fk in fks:
            parent, column = fk['parent'], fk['column']
            rule = rules['m2o'].get((table, column)) if options['follow_links'] else None
            is_header = len(headers) == 1 and fk is headers[0] and table != 'account_partial_reconcile'
            parent_kind = self._kind(data, parent)
            if parent_kind != 'transaction':
                continue
            values = self._fetch_ids(SQL('SELECT DISTINCT %s FROM %s WHERE id = ANY(%s) AND %s IS NOT NULL',
                                   SQL.identifier(column), SQL.identifier(table), ids, SQL.identifier(column)))
            values -= plan.delete.get(parent, set())
            if not values:
                continue
            if is_header:
                add(parent, values, 'header')
            elif rule in ('pull', 'both'):
                add(parent, values, 'pull')
            else:
                # a kept document loses one of its lines or references: its totals are recomputed
                plan.neighbours[parent] |= values

    @api.model
    def _plan_reconcile(self, data, plan, ids, add):
        """ The entries reconciled with the deleted journal items (the payment of a deleted invoice) go with
        them, one level deep: the reconciliations of those entries with other documents are only undone. """
        if 'account_partial_reconcile' not in data['id_tables']:
            return
        cr = self.env.cr
        cr.execute("SELECT id, move_id FROM account_move_line WHERE id = ANY(%s)", [ids])
        own = [line for line, move in cr.fetchall() if move not in plan.reconcile_moves]
        if not own:
            return
        cr.execute("""
            SELECT DISTINCT l.move_id
              FROM account_partial_reconcile p
              JOIN account_move_line l ON l.id IN (p.debit_move_id, p.credit_move_id)
             WHERE (p.debit_move_id = ANY(%s) OR p.credit_move_id = ANY(%s)) AND NOT l.id = ANY(%s)
        """, [own, own, own])
        moves = {row[0] for row in cr.fetchall()} - plan.delete.get('account_move', set())
        if moves:
            plan.reconcile_moves |= moves
            add('account_move', moves, 'reconcile')

    @api.model
    def _nullify(self, plan, fk, parent_ids, rows, neighbour=False):
        plan.nullify[(fk['child'], fk['column'])] |= set(parent_ids)
        plan.nullify_rows[(fk['child'], fk['column'])] |= set(rows)
        if neighbour:
            plan.neighbours[fk['child']] |= set(rows)

    @api.model
    def _check_strict(self, data, plan):
        """ Strict mode: no other document may be reached """
        for table, ids in plan.delete.items():
            model = data['table_model'].get(table)
            extra = ids - plan.seed.get(table, set())
            if model in data['roots'] and extra:
                plan.blockers.append(_(
                    'Mode ketat: %(count)s dokumen %(label)s lain ikut terhapus. Aktifkan "Hapus beserta turunan" '
                    'atau pilih dokumen itu juga.', count=len(extra), label=self._table_label(data, table)))

    @api.model
    def _table_label(self, data, table):
        model = data['table_model'].get(table)
        if model:
            return '%s (%s)' % (self.env[model]._description or model, model)
        return table

    @api.model
    def _blocker_text(self, data, fk, rows):
        return _(
            '%(count)s record %(label)s merujuk data yang akan dihapus lewat kolom "%(column)s" yang wajib diisi '
            '(%(kind)s). Record itu tidak boleh ikut terhapus, jadi pembersihan ini ditolak. Ubah klasifikasinya '
            'atau sertakan pilihan lain.',
            count=len(rows), label=self._table_label(data, fk['child']), column=fk['column'],
            kind=KIND_LABELS.get(self._kind(data, fk['child']), ''))

    # ------------------------------------------------------------------
    # Describing a plan
    # ------------------------------------------------------------------
    @api.model
    def describe(self, plan, data):
        """ The lines of the preview and the warnings """
        lines = []
        targets = {t.model_name: t for t in self.env['x.cleanup.target'].sudo().search([])}
        for table, ids in plan.delete.items():
            model = data['table_model'].get(table)
            target = targets.get(model)
            kind = self._kind(data, table)
            lines.append({
                'table_name': table,
                'model': model or False,
                'label': (self.env[model]._description if model else table),
                'area': target.area if target else False,
                'kind': kind,
                'action': 'delete',
                'count': len(ids),
                'seed_count': len(plan.seed.get(table, ())),
                'reason': ', '.join(REASON_LABELS.get(r, r) for r in sorted(plan.reasons[table])),
            })
        for (table, column), rows in plan.nullify_rows.items():
            model = data['table_model'].get(table)
            target = targets.get(model)
            lines.append({
                'table_name': table,
                'model': model or False,
                'label': (self.env[model]._description if model else table),
                'area': target.area if target else False,
                'kind': self._kind(data, table),
                'action': 'nullify',
                'count': len(rows),
                'reason': _('Kolom "%s" dikosongkan (record tetap ada)', column),
            })
        relation_counts = defaultdict(int)
        for (rel, column), ids in plan.relation.items():
            self.env.cr.execute(SQL('SELECT count(*) FROM %s WHERE %s = ANY(%s)',
                                    SQL.identifier(rel), SQL.identifier(column), list(ids)))
            relation_counts[rel] += self.env.cr.fetchone()[0]
        for rel, count in relation_counts.items():
            if count:
                lines.append({'table_name': rel, 'model': False, 'label': rel, 'kind': 'relation',
                              'action': 'relation', 'count': count, 'reason': _('Baris relasi many2many')})
        return lines

    @api.model
    def warnings(self, plan, data):
        """ The documents reached outside the selection, the unclassified tables, the notes """
        parts = []
        for table, ids in sorted(plan.delete.items()):
            model = data['table_model'].get(table)
            extra = ids - plan.seed.get(table, set())
            if model in data['roots'] and extra and plan.seed:
                names = self._sample_names(model, extra)
                parts.append(('warning', _(
                    '%(count)s dokumen %(label)s di luar pilihan ikut terhapus: %(names)s',
                    count=len(extra), label=self.env[model]._description or model, names=names)))
        for table, ids in sorted(plan.unclassified.items()):
            parts.append(('warning', _(
                '%(count)s record %(label)s belum diklasifikasi tapi ikut terhapus karena wajib terikat ke data '
                'yang dihapus. Klasifikasikan modelnya bila perlu.', count=len(ids),
                label=self._table_label(data, table))))
        if plan.reconcile_moves:
            parts.append(('info', _(
                '%s jurnal (pembayaran/lawan rekonsiliasi) ikut terhapus karena terekonsiliasi dengan dokumen '
                'yang dihapus. Rekonsiliasinya dengan dokumen lain dilepas; dokumen lain itu menjadi belum lunas.',
                len(plan.reconcile_moves))))
        for note in plan.notes:
            parts.append(('info', note))
        return parts

    @api.model
    def _sample_names(self, model, ids):
        ids = sorted(ids)
        try:
            records = self.env[model].sudo().with_context(active_test=False).browse(ids[:SAMPLE])
            names = ', '.join(records.mapped('display_name'))
        except Exception:  # noqa: BLE001 - a custom display_name must not break the preview
            names = ', '.join(str(i) for i in ids[:SAMPLE])
        if len(ids) > SAMPLE:
            names += _(' dan %s lainnya', len(ids) - SAMPLE)
        return names

    # ------------------------------------------------------------------
    # Running a plan
    # ------------------------------------------------------------------
    @api.model
    def simulate(self, plan, data, options=None):
        """ Run the plan in a savepoint and roll it back. Returns (ok, message). """
        result = {}
        try:
            with self.env.cr.savepoint(flush=False):
                result = self._execute(plan, data, dict(options or {}, dry_run=True))
                raise _DryRunRollback()
        except _DryRunRollback:
            ok, message = True, _('Simulasi berhasil: %s baris bisa dihapus tanpa ditolak database.',
                                  result.get('deleted_total', 0))
        except UserError as e:
            ok, message = False, str(e.args[0] if e.args else e)
        except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
            raise
        except psycopg2.Error as e:
            ok, message = False, (e.pgerror or str(e)).strip()
        finally:
            self.env.invalidate_all(flush=False)
        return ok, message

    @api.model
    def execute(self, plan, data, options=None):
        """ Run the plan for good, in the current transaction """
        if plan.blockers:
            raise UserError('\n'.join(plan.blockers))
        result = self._execute(plan, data, dict(options or {}, dry_run=False))
        self.env.registry.clear_cache()
        return result

    @api.model
    def _execute(self, plan, data, options):
        cr = self.env.cr
        self.env.flush_all()
        result = {'deleted': {}, 'nullified': {}, 'post': []}
        attachments = []

        # 1. what needs the ORM, while the records still exist
        if options.get('adjust_quants'):
            result['post'] += self._adjust_quants(plan, data)
        fleet_ids = self._fleet_touched(plan, data) if options.get('reset_fleet') else set()
        if not options.get('dry_run'):
            attachments = self._attachment_files(plan, data)
        self.env.flush_all()

        # 2. empty the references that are kept
        for (table, column), parent_ids in plan.nullify.items():
            rows = plan.nullify_rows.get((table, column))
            if not rows:
                continue
            cr.execute(SQL('UPDATE %s SET %s = NULL WHERE id = ANY(%s) AND %s = ANY(%s)',
                           SQL.identifier(table), SQL.identifier(column), list(rows),
                           SQL.identifier(column), list(parent_ids)))
            result['nullified']['%s.%s' % (table, column)] = cr.rowcount

        # 3. the many2many rows the database does not cascade
        for (rel, column), ids in plan.relation.items():
            cr.execute(SQL('DELETE FROM %s WHERE %s = ANY(%s)', SQL.identifier(rel), SQL.identifier(column),
                           list(ids)))

        # 4. delete, retrying what a foreign key refuses; break the cycles of references
        pending = {table: list(ids) for table, ids in plan.delete.items() if ids}
        errors = {}
        for _pass in range(MAX_PASSES):
            progress = False
            for table in list(pending):
                ids = pending[table]
                try:
                    with cr.savepoint(flush=False):
                        cr.execute(SQL('DELETE FROM %s WHERE id = ANY(%s)', SQL.identifier(table), ids),
                                   log_exceptions=False)
                    del pending[table]
                    errors.pop(table, None)
                    progress = True
                except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                    raise
                except psycopg2.Error as e:
                    errors[table] = (e.pgerror or str(e)).strip()
            if not pending:
                break
            if not progress and not self._break_cycles(data, pending):
                break
        if pending:
            details = '\n'.join('- %s: %s' % (self._table_label(data, t), errors.get(t, '').splitlines()[0]
                                              if errors.get(t) else '') for t in pending)
            raise UserError(_('Database menolak menghapus tabel berikut, jadi tidak ada yang dihapus:\n%s', details))
        for table, ids in plan.delete.items():
            result['deleted'][table] = len(ids)
        result['deleted_total'] = sum(result['deleted'].values())

        # 5. what is attached to the deleted documents, by model name
        for table, ids in plan.delete.items():
            model = data['table_model'].get(table)
            if not model or not ids:
                continue
            for link_table, model_column, id_column in LINKED_TABLES:
                if link_table not in data['id_tables']:
                    continue
                try:
                    with cr.savepoint(flush=False):
                        cr.execute(SQL('DELETE FROM %s WHERE %s = %s AND %s = ANY(%s)', SQL.identifier(link_table),
                                       SQL.identifier(model_column), model, SQL.identifier(id_column), list(ids)),
                                   log_exceptions=False)
                except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                    raise
                except psycopg2.Error as e:
                    result['post'].append(_('%(table)s milik %(model)s tidak terhapus: %(error)s', table=link_table,
                                            model=model, error=(e.pgerror or str(e)).strip().splitlines()[0]))
        self._delete_orphan_reconciles(data)

        # 6. after-care
        if options.get('clear_lock_dates'):
            result['post'] += self._clear_lock_dates()
        if options.get('reset_fleet'):
            result['post'] += self._reset_fleet(fleet_ids, options)
        self.env.invalidate_all(flush=False)
        result['post'] += self._recompute_neighbours(plan, data)
        if options.get('reset_sequences') and not options.get('dry_run'):
            count = self.env['x.cleanup.sequence.wizard']._reset_sequences(
                self.env['x.cleanup.sequence.wizard']._transaction_sequences(), 1)
            result['post'].append(_('%s sequence direset ke 1.', count))
        if not options.get('dry_run'):
            Attachment = self.env['ir.attachment']
            for fname in attachments:
                try:
                    Attachment._file_delete(fname)
                except Exception:  # noqa: BLE001 - a missing file is no reason to undo the cleanup
                    _logger.warning('Data Cleanup: could not mark %s for garbage collection', fname)
        return result

    @api.model
    def _break_cycles(self, data, pending):
        """ Rows refusing each other's deletion: empty their references to the other pending rows """
        broken = False
        cr = self.env.cr
        for table, ids in pending.items():
            for fk in data['outgoing'].get(table, []):
                if fk['notnull'] or fk['parent'] not in pending:
                    continue
                cr.execute(SQL('UPDATE %s SET %s = NULL WHERE id = ANY(%s) AND %s = ANY(%s)',
                               SQL.identifier(table), SQL.identifier(fk['column']), ids,
                               SQL.identifier(fk['column']), pending[fk['parent']]))
                broken = broken or bool(cr.rowcount)
        return broken

    @api.model
    def _delete_orphan_reconciles(self, data):
        if 'account_full_reconcile' not in data['id_tables']:
            return
        self.env.cr.execute("""
            DELETE FROM account_full_reconcile f
             WHERE NOT EXISTS (SELECT 1 FROM account_move_line l WHERE l.full_reconcile_id = f.id)
        """)

    @api.model
    def _attachment_files(self, plan, data):
        files = []
        for table, ids in plan.delete.items():
            model = data['table_model'].get(table)
            if model and ids:
                self.env.cr.execute("""
                    SELECT store_fname FROM ir_attachment
                     WHERE res_model = %s AND res_id = ANY(%s) AND store_fname IS NOT NULL
                """, [model, list(ids)])
                files += [row[0] for row in self.env.cr.fetchall()]
        return files

    @api.model
    def _adjust_quants(self, plan, data):
        """ Undo on the quants what the deleted stock move lines did, unless the quants are cleared too """
        line_ids = plan.delete.get('stock_move_line')
        if not line_ids or 'stock.quant' not in self.env:
            return []
        self.env.cr.execute('SELECT count(*) FROM stock_quant')
        if len(plan.delete.get('stock_quant', ())) >= self.env.cr.fetchone()[0]:
            return []
        Quant = self.env['stock.quant'].sudo()
        lines = self.env['stock.move.line'].sudo().with_context(active_test=False).browse(list(line_ids))
        done = reserved = failed = 0
        for line in lines:
            try:
                product = line.product_id
                if not product or product.type != 'consu' or not getattr(product, 'is_storable', True):
                    continue
                qty = line.product_uom_id._compute_quantity(line.quantity, product.uom_id, rounding_method='HALF-UP')
                if not qty:
                    continue
                if line.state == 'done':
                    if line.location_dest_id.usage in ('internal', 'transit'):
                        Quant._update_available_quantity(product, line.location_dest_id, quantity=-qty,
                                                         lot_id=line.lot_id, package_id=line.result_package_id,
                                                         owner_id=line.owner_id)
                    if line.location_id.usage in ('internal', 'transit'):
                        Quant._update_available_quantity(product, line.location_id, quantity=qty,
                                                         lot_id=line.lot_id, package_id=line.package_id,
                                                         owner_id=line.owner_id)
                    done += 1
                elif line.state not in ('cancel',) and line.location_id.usage in ('internal', 'transit'):
                    Quant._update_reserved_quantity(product, line.location_id, -qty, lot_id=line.lot_id,
                                                    package_id=line.package_id, owner_id=line.owner_id, strict=True)
                    reserved += 1
            except Exception as e:  # noqa: BLE001 - reported, the cleanup goes on
                failed += 1
                _logger.warning('Data Cleanup: quant of move line %s not adjusted: %s', line.id, e)
        notes = []
        if done or reserved:
            notes.append(_('Stok on hand disesuaikan untuk %(done)s baris move selesai dan %(res)s reservasi dilepas.',
                           done=done, res=reserved))
        if failed:
            notes.append(_('%s baris move gagal disesuaikan ke stok; cek stok on hand produk terkait.', failed))
        return notes

    @api.model
    def _fleet_touched(self, plan, data):
        """ The vehicles the deleted rows point at, or every vehicle when the whole fleet area is cleared """
        if 'fleet_vehicle' not in data['id_tables']:
            return set()
        vehicles = set()
        for table, ids in plan.delete.items():
            for fk in data['outgoing'].get(table, []):
                if fk['parent'] == 'fleet_vehicle':
                    vehicles |= self._fetch_ids(SQL('SELECT DISTINCT %s FROM %s WHERE id = ANY(%s)',
                                              SQL.identifier(fk['column']), SQL.identifier(table), list(ids)))
        return vehicles

    @api.model
    def _reset_fleet(self, vehicle_ids, options):
        if options.get('fleet_all'):
            vehicle_ids = self._fetch_ids(SQL('SELECT id FROM fleet_vehicle'))
        if not vehicle_ids:
            return []
        cr = self.env.cr
        cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'fleet_vehicle'")
        columns = {row[0] for row in cr.fetchall()}
        sets = []
        if options.get('fleet_state_id') and 'state_id' in columns:
            sets.append(SQL('state_id = %s', int(options['fleet_state_id'])))
        if options.get('fleet_substatus_id') and 'fleet_sub_status_id' in columns:
            sets.append(SQL('fleet_sub_status_id = %s', int(options['fleet_substatus_id'])))
        if options.get('fleet_clear_customer') and 'last_customer_id' in columns:
            sets.append(SQL('last_customer_id = NULL'))
        if not sets:
            return []
        cr.execute(SQL('UPDATE fleet_vehicle SET %s WHERE id = ANY(%s)', SQL(', ').join(sets), list(vehicle_ids)))
        return [_('Status %s unit fleet direset.', cr.rowcount)]

    @api.model
    def _clear_lock_dates(self):
        cr = self.env.cr
        cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'res_company'")
        columns = {row[0] for row in cr.fetchall()}
        lock = [c for c in ('fiscalyear_lock_date', 'tax_lock_date', 'sale_lock_date', 'purchase_lock_date',
                            'hard_lock_date') if c in columns]
        if not lock:
            return []
        cr.execute(SQL('UPDATE res_company SET %s', SQL(', ').join(SQL('%s = NULL', SQL.identifier(c)) for c in lock)))
        return [_('Lock date akuntansi dikosongkan.')]

    @api.model
    def _recompute_neighbours(self, plan, data):
        """ The kept transactions that lost lines, references or reconciliations: their stored computed
        fields (totals, invoiced and delivered quantities, residual amounts, states) are computed again """
        notes, failed = [], []
        count = 0
        for table, ids in plan.neighbours.items():
            model_name = data['table_model'].get(table)
            if not ids or not model_name or self._kind(data, table) != 'transaction':
                continue
            model = self.env[model_name].sudo().with_context(active_test=False)
            existing = self._fetch_ids(SQL('SELECT id FROM %s WHERE id = ANY(%s)', SQL.identifier(table), list(ids)))
            records = model.browse(list(existing))
            if not records:
                continue
            # editable computed fields (a price or a quantity typed by hand) are left alone
            editable = RECOMPUTE_EDITABLE.get(model_name, set())
            stored = [f for f in model._fields.values()
                      if f.store and f.compute and (f.readonly or f.name in editable)]
            try:
                with self.env.cr.savepoint():
                    for field in stored:
                        self.env.add_to_compute(field, records)
                    self.env.flush_all()
                count += len(records)
            except Exception as e:  # noqa: BLE001 - reported, the cleanup goes on
                self.env.invalidate_all(flush=False)
                failed.append('%s (%s)' % (model_name, str(e).splitlines()[0] if str(e) else type(e).__name__))
        if count:
            notes.append(_('%s record terkait yang dipertahankan dihitung ulang (total, qty, status).', count))
        if failed:
            notes.append(_('Gagal menghitung ulang: %s', ', '.join(failed)))
        return notes

    # ------------------------------------------------------------------
    # Entry points used by the wizard
    # ------------------------------------------------------------------
    @api.model
    def seed_dumps(self, seed):
        return json.dumps({model: (ids if ids == 'all' else sorted(ids)) for model, ids in seed.items()})

    @api.model
    def seed_loads(self, text):
        return json.loads(text or '{}')

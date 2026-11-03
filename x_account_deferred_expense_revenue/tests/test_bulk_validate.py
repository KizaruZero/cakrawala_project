from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


class DeferredLifecycleCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.journal = cls.env['account.journal'].create({
            'name': 'Deferred Bulk Validation QA', 'code': 'DBQA', 'type': 'general',
            'company_id': cls.company.id,
        })
        cls.accounts = {}
        for index, (key, account_type) in enumerate([
            ('liability', 'liability_current'), ('revenue', 'income'),
            ('asset', 'asset_current'), ('expense', 'expense'),
        ], 1):
            cls.accounts[key] = cls.env['account.account'].create({
                'name': 'Deferred Bulk QA ' + key, 'code': '7999980%s' % index,
                'account_type': account_type, 'company_ids': [Command.set(cls.company.ids)],
            })
        cls.models = {}
        for kind, deferred, recognition in [('revenue', 'liability', 'revenue'), ('expense', 'asset', 'expense')]:
            cls.models[kind] = cls.env['account.deferred.model'].create({
                'name': 'Deferred Bulk QA ' + kind, 'deferred_type': kind,
                'company_id': cls.company.id, 'method_number': 3, 'method_period': 1,
                'deferred_account_id': cls.accounts[deferred].id,
                'recognition_account_id': cls.accounts[recognition].id,
                'journal_id': cls.journal.id,
            })
        cls.Entry = cls.env['account.deferred.entry']

    def _entry(self, kind='revenue', **values):
        return self.Entry.create({
            'name': 'Deferred Bulk QA ' + kind, 'deferred_type': kind,
            'model_id': self.models[kind].id, 'company_id': self.company.id,
            'date': fields.Date.context_today(self.Entry) - relativedelta(months=1),
            'original_value': 12000, **values,
        })

@tagged('post_install', '-at_install')
class TestDeferredBulkValidate(DeferredLifecycleCommon):

    def test_server_action_is_bound_to_both_deferred_menus(self):
        action = self.env.ref('x_account_deferred_expense_revenue.action_validate_deferred_selected')
        self.assertEqual(action.name, 'Validate')
        self.assertEqual(action.binding_model_id.model, 'account.deferred.entry')
        self.assertEqual(action.binding_view_types, 'list')
        for xmlid in ['action_account_deferred_revenue', 'action_account_deferred_expense']:
            self.assertEqual(self.env.ref('x_account_deferred_expense_revenue.' + xmlid).res_model, action.binding_model_id.model)

    def test_revenue_and_expense_use_existing_validation_and_future_autopost(self):
        entries = self._entry('revenue') | self._entry('expense')
        result = entries.action_validate_selected()
        self.assertEqual(result['params']['type'], 'success')
        self.assertIn('Validated 2', result['params']['message'])
        self.assertEqual(set(entries.mapped('state')), {'running'})
        for entry in entries:
            self.assertEqual(len(entry.line_ids), 3)
            self.assertEqual(len(entry.line_ids.move_id), 3)
            self.assertEqual(len(entry.line_ids.filtered(lambda line: line.state == 'posted')), 2)
            self.assertEqual(entry.recognized_value, 8000)
            self.assertEqual(entry.residual_value, 4000)
            future = entry.line_ids.filtered(lambda line: line.date > fields.Date.context_today(entry))
            self.assertEqual(future.move_id.state, 'draft')
            self.assertEqual(future.move_id.auto_post, 'at_date')
            for move in entry.line_ids.move_id:
                self.assertTrue(entry.currency_id.is_zero(sum(move.line_ids.mapped('balance'))))

    def test_non_drafts_are_not_reopened_or_posted_twice(self):
        running = self._entry()
        running.action_validate()
        closed = self._entry(date=fields.Date.context_today(self.Entry) - relativedelta(months=6))
        closed.action_validate()
        self.assertEqual(closed.state, 'closed')
        cancelled = self._entry()
        cancelled.action_cancel()
        old = running | closed | cancelled
        before = (old.mapped('state'), old.line_ids.move_id.ids,
                  old.line_ids.move_id.read(['state', 'date', 'auto_post']))
        draft = self._entry('expense')
        result = (old | draft).action_validate_selected()
        self.assertIn('Validated 1', result['params']['message'])
        self.assertIn('Skipped 3', result['params']['message'])
        self.assertEqual((old.mapped('state'), old.line_ids.move_id.ids,
                          old.line_ids.move_id.read(['state', 'date', 'auto_post'])), before)
        self.assertEqual(old.action_validate_selected()['params']['type'], 'warning')

    def test_duplicate_selection_and_repeat_do_not_duplicate_moves(self):
        entry = self._entry()
        self.Entry.browse([entry.id, entry.id]).action_validate_selected()
        moves = entry.line_ids.move_id
        entry.action_validate_selected()
        self.assertEqual(entry.line_ids.move_id, moves)
        self.assertEqual(len(moves), 3)

    def test_empty_selection_is_a_warning(self):
        result = self.Entry.action_validate_selected()
        self.assertEqual(result['params']['type'], 'warning')
        self.assertIn('Validated 0', result['params']['message'])

    def test_internal_user_without_deferred_rights_cannot_validate(self):
        entry = self._entry()
        user = new_test_user(self.env, login='deferred_bulk_no_access', groups='base.group_user', company_id=self.company.id)
        with self.assertRaises(AccessError):
            entry.with_user(user).action_validate_selected()
        self.assertEqual(entry.state, 'draft')
        self.assertFalse(entry.line_ids.move_id)

    def test_bound_server_action_executes_validation(self):
        entry = self._entry()
        action = self.env.ref('x_account_deferred_expense_revenue.action_validate_deferred_selected')
        result = action.with_context(active_model=entry._name, active_ids=entry.ids).run()
        self.assertEqual(result['params']['type'], 'success')
        self.assertEqual(entry.state, 'running')

    def test_other_active_company_cannot_validate_this_company_items(self):
        values = {'name': 'Deferred Bulk QA Other Company', 'currency_id': self.company.currency_id.id}
        if 'company_code' in self.env['res.company']._fields:
            values['company_code'] = 'DBQ2'
        other = self.env['res.company'].create(values)
        entry = self._entry()
        with self.assertRaises(AccessError):
            entry.with_context(allowed_company_ids=other.ids).action_validate_selected()
        self.assertEqual(entry.state, 'draft')
        self.assertFalse(entry.line_ids.move_id)

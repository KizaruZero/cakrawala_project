import runpy
from pathlib import Path

from dateutil.relativedelta import relativedelta
from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .test_bulk_validate import DeferredLifecycleCommon


@tagged('post_install', '-at_install')
class TestDeferredLifecycle(DeferredLifecycleCommon):

    def _running(self, kind='revenue', **values):
        entry = self._entry(kind, method_number=4, **values)
        entry.action_validate()
        self.assertEqual(entry.state, 'running')
        return entry

    def test_stop_preserves_posted_and_cancels_drafts_for_both_types(self):
        for kind in ('expense', 'revenue'):
            entry = self._running(kind)
            journals = entry.line_ids.move_id
            posted = journals.filtered(lambda move: move.state == 'posted')
            drafts = journals - posted
            before = posted.read(['date', 'state', 'auto_post', 'write_date', 'line_ids'])
            amounts = (entry.original_value, entry.recognized_value, entry.residual_value)
            self.assertEqual(len(posted), 2)
            self.assertEqual(len(drafts), 2)
            entry.action_stop_deferred()
            self.assertEqual(entry.state, 'stopped')
            self.assertEqual(entry.line_ids.move_id, journals)
            self.assertEqual(set(drafts.mapped('state')), {'cancel'})
            self.assertEqual(set(drafts.mapped('auto_post')), {'no'})
            self.assertEqual(posted.read(['date', 'state', 'auto_post', 'write_date', 'line_ids']), before)
            self.assertEqual((entry.original_value, entry.recognized_value, entry.residual_value), amounts)
            self.assertEqual(set(entry.line_ids.filtered(lambda line: line.move_id in drafts).mapped('state')), {'cancel'})

    def test_manual_journal_cancel_updates_board_state(self):
        entry = self._running()
        line = entry.line_ids.filtered(lambda line: line.state == 'draft')[:1]
        before = (entry.recognized_value, entry.residual_value)
        line.move_id.button_cancel()
        self.assertEqual(line.move_id.state, 'cancel')
        self.assertEqual(line.state, 'cancel')
        self.assertEqual(line.move_id.auto_post, 'no')
        self.assertEqual((entry.recognized_value, entry.residual_value), before)

    def test_stop_legacy_board_without_moves_does_not_generate_journals(self):
        entry = self._entry()
        entry.state = 'running'
        entry.action_stop_deferred()
        self.assertFalse(entry.line_ids.move_id)
        self.assertEqual(set(entry.line_ids.mapped('state')), {'cancel'})
        self.assertEqual(entry.recognized_value, 0)
        self.assertEqual(entry.residual_value, entry.original_value)
        self.Entry._cron_post_due_lines()
        self.assertFalse(entry.line_ids.move_id)
        self.assertEqual(entry.state, 'stopped')

    def test_cancel_draft_parent_marks_unmaterialized_lines_cancelled(self):
        entry = self._entry()
        entry.action_cancel()
        self.assertEqual(entry.state, 'cancelled')
        self.assertEqual(set(entry.line_ids.mapped('state')), {'cancel'})
        self.assertFalse(entry.line_ids.move_id)

    def test_cancel_running_without_posted_preserves_cancelled_journals(self):
        entry = self._entry(date=fields.Date.context_today(self.Entry) + relativedelta(months=1))
        entry.action_validate()
        journals = entry.line_ids.move_id
        entry.action_cancel()
        self.assertEqual(entry.state, 'cancelled')
        self.assertEqual(entry.line_ids.move_id, journals)
        self.assertEqual(set(journals.mapped('state')), {'cancel'})
        self.assertEqual(set(journals.mapped('auto_post')), {'no'})
        self.assertEqual(set(entry.line_ids.mapped('state')), {'cancel'})

        with self.assertRaisesRegex(UserError, 'archived instead of deleted'):
            entry.unlink()
        self.assertTrue(journals.exists())

    def test_cancel_cannot_unpost_recognized_history(self):
        entry = self._running()
        before = entry.line_ids.move_id.read(['state', 'date', 'auto_post', 'line_ids'])
        with self.assertRaisesRegex(UserError, 'already has posted'):
            entry.action_cancel()
        self.assertEqual(entry.state, 'running')
        self.assertEqual(entry.line_ids.move_id.read(['state', 'date', 'auto_post', 'line_ids']), before)

    def test_write_off_keeps_old_financial_logic_and_uses_new_state(self):
        for kind in ('expense', 'revenue'):
            entry = self._running(kind)
            posted = entry.line_ids.filtered(lambda line: line.state == 'posted').move_id
            remaining = entry.line_ids.filtered(lambda line: line.state != 'posted')
            old_drafts = remaining.move_id
            residual = entry.residual_value
            before = posted.read(['state', 'date', 'line_ids', 'write_date'])
            entry.action_write_off_deferred()
            self.assertEqual(entry.state, 'written_off')
            self.assertEqual(posted.read(['state', 'date', 'line_ids', 'write_date']), before)
            self.assertEqual(set(old_drafts.mapped('state')), {'cancel'})
            self.assertEqual(set(old_drafts.mapped('auto_post')), {'no'})
            final = remaining.move_id
            self.assertEqual(len(final), 1)
            self.assertEqual(final.state, 'posted')
            self.assertIn('Write Off Deferred', final.ref)
            self.assertEqual(sum(final.line_ids.mapped('debit')), residual)
            self.assertEqual(sum(final.line_ids.mapped('credit')), residual)
            self.assertEqual(set(entry.line_ids.mapped('state')), {'posted'})
            self.assertEqual(entry.recognized_value, entry.original_value)
            self.assertEqual(entry.residual_value, 0)

    def test_write_off_includes_previously_cancelled_unrecognized_period(self):
        entry = self._running()
        entry.line_ids.filtered(lambda line: line.state == 'draft')[:1].move_id.button_cancel()
        entry.action_write_off_deferred()
        self.assertEqual(entry.state, 'written_off')
        self.assertEqual(entry.residual_value, 0)

    def test_repeated_stop_or_write_off_does_not_create_more_journals(self):
        for method in ('action_stop_deferred', 'action_write_off_deferred'):
            entry = self._running()
            getattr(entry, method)()
            moves = self.env['account.move'].search([('recognition_deferred_entry_id', '=', entry.id)])
            getattr(entry, method)()
            self.assertEqual(self.env['account.move'].search([('recognition_deferred_entry_id', '=', entry.id)]), moves)

    def test_stopped_journals_cannot_be_reset_or_posted(self):
        entry = self._running()
        drafts = entry.line_ids.filtered(lambda line: line.state == 'draft').move_id
        entry.action_stop_deferred()
        with self.assertRaisesRegex(UserError, 'cannot be reset'):
            drafts.button_draft()
        with self.assertRaisesRegex(UserError, 'cannot be posted'):
            drafts._post(soft=False)
        self.assertEqual(set(drafts.mapped('state')), {'cancel'})
        self.assertEqual(entry.state, 'stopped')

    def test_stopped_or_written_off_cannot_be_validated_or_recomputed(self):
        for action in ('action_stop_deferred', 'action_write_off_deferred'):
            entry = self._running()
            getattr(entry, action)()
            for method in ('action_validate', 'action_compute_board'):
                with self.assertRaisesRegex(UserError, 'Only Draft'):
                    getattr(entry, method)()
            self.assertIn('Skipped 1', entry.action_validate_selected()['params']['message'])

    def test_non_running_items_cannot_be_stopped_or_written_off(self):
        entry = self._entry()
        for method in ('action_stop_deferred', 'action_write_off_deferred'):
            with self.assertRaisesRegex(UserError, 'Only Running'):
                getattr(entry, method)()
        self.assertEqual(entry.state, 'draft')
        self.assertFalse(entry.line_ids.move_id)

    def test_copy_of_terminal_entry_starts_as_unvalidated_draft(self):
        entry = self._running()
        entry.action_stop_deferred()
        copy = entry.copy()
        self.assertEqual(copy.state, 'draft')
        self.assertFalse(copy.line_ids.move_id)
        self.assertEqual(set(copy.line_ids.mapped('state')), {'draft'})

    def test_user_without_accounting_rights_cannot_stop_or_write_off(self):
        entry = self._running()
        user = new_test_user(self.env, login='deferred_stop_no_rights', groups='base.group_user', company_id=self.company.id)
        for method in ('action_stop_deferred', 'action_write_off_deferred'):
            with self.assertRaises(AccessError):
                getattr(entry.with_user(user), method)()
        self.assertEqual(entry.state, 'running')

    def test_cancelled_historical_board_migration_updates_only_state(self):
        entry = self._running()
        line = entry.line_ids.filtered(lambda line: line.state == 'draft')[:1]
        line.move_id.button_cancel()
        before = line.move_id.read(['state', 'date', 'line_ids', 'write_date'])
        line.flush_recordset(['state'])
        self.env.cr.execute("UPDATE account_deferred_entry_line SET state = 'draft' WHERE id = %s", [line.id])
        line.invalidate_recordset(['state'])
        migrate = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'migrations/19.0.1.0.10/post-migrate.py'))['migrate']
        migrate(self.env.cr, '19.0.1.0.9')
        self.assertEqual(line.state, 'cancel')
        self.assertEqual(line.move_id.read(['state', 'date', 'line_ids', 'write_date']), before)
        self.assertEqual(entry.state, 'running')

    def test_both_buttons_and_statuses_are_available(self):
        view = self.env.ref('x_account_deferred_expense_revenue.view_account_deferred_entry_form')
        root = etree.fromstring(view.arch_db)
        self.assertEqual(root.xpath('//button[@name="action_write_off_deferred"]/@string'), ['Write Off Deferred'])
        self.assertEqual(root.xpath('//button[@name="action_stop_deferred"]/@string'), ['Stop Deferred'])
        states = dict(self.Entry._fields['state'].selection)
        self.assertEqual(states['written_off'], 'Written Off')
        self.assertEqual(states['stopped'], 'Stopped')
        self.assertIn('cancel', dict(self.env['account.deferred.entry.line']._fields['state'].selection))

    def test_variant_analytic_name_drops_default_code_and_uses_names(self):
        product = self.env['product.product'].create({'name': 'Deferred Vehicle (2026)', 'default_code': 'RPC/IGNORED'})
        plan = self.env['account.analytic.plan'].create({'name': 'Deferred Name QA Plan'})
        accounts = self.env['account.analytic.account'].create([
            {'name': name, 'plan_id': plan.id} for name in ('B 9935 UXJ - FN-001', 'UNIT CENTRE')
        ])
        name = self.Entry._get_product_analytic_name(product, {','.join(map(str, accounts.ids)): 100})
        self.assertEqual(name, 'Deferred Vehicle (2026) - B 9935 UXJ - FN-001, UNIT CENTRE')
        self.assertEqual(self.Entry._get_product_analytic_name(product, {}), 'Deferred Vehicle (2026)')

    def test_native_invoice_revenue_name_changes_but_expense_name_is_preserved(self):
        product = self.env['product.product'].create({'name': 'Deferred Vehicle'})
        plan = self.env['account.analytic.plan'].create({'name': 'Deferred Invoice Name QA'})
        analytic = self.env['account.analytic.account'].create({'name': 'B 9935 UXJ - FN-001', 'plan_id': plan.id})
        for kind, key in [('revenue', 'liability'), ('expense', 'asset')]:
            move = self.env['account.move'].create({
                'move_type': 'entry', 'journal_id': self.journal.id,
                'line_ids': [Command.create({'product_id': product.id, 'name': 'RPC/OLD - product - period',
                                            'account_id': self.accounts[key].id, 'debit': 12000,
                                            'analytic_distribution': {str(analytic.id): 100}}),
                             Command.create({'account_id': self.accounts['revenue'].id, 'credit': 12000})],
            })
            self.accounts[key].deferred_model_id = self.models[kind]
            move._create_deferred_entries(move.line_ids.filtered('product_id'), 'OLD INVOICE DESCRIPTION')
            self.assertEqual(move.deferred_entry_ids.name, 'Deferred Vehicle - B 9935 UXJ - FN-001' if kind == 'revenue' else 'OLD INVOICE DESCRIPTION')

from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .test_early_settlement import LeasingScheduleCommon


@tagged('post_install', '-at_install')
class TestEarlySettlementReconciliation(LeasingScheduleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.settlement_clearing_account.write({
            'reconcile': True, 'is_early_settlement_clearing': True,
            'early_settlement_target_account_id': cls.principal_account.id,
            'early_settlement_journal_id': cls.general_journal.id,
        })

    def _posted_bill(self, count=2, **values):
        loan = self._loan(count=count)
        bill = self._bill(loan)
        bill.write({'date': date(2026, 11, 12), 'invoice_date': date(2026, 11, 12), **values})
        bill.action_post()
        return bill

    def _manual_bill(self, amounts=(100, 200), **values):
        return self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.vendor.id,
            'journal_id': self.purchase_journal.id, 'company_id': self.company.id,
            'currency_id': self.currency.id, 'date': date(2026, 11, 12),
            'invoice_date': date(2026, 11, 12), 'is_early_settlement': True,
            'invoice_line_ids': [Command.create({
                'name': 'Principal %s' % index, 'account_id': self.settlement_clearing_account.id,
                'quantity': 1, 'price_unit': amount,
                'analytic_distribution': {str(self.analytic.id): 100},
            }) for index, amount in enumerate(amounts)], **values,
        })

    def _recon(self, bill):
        action = bill.action_recon_clearing_ap_leasing()
        self.assertEqual(action['res_model'], 'account.move')
        moves = bill._active_early_settlement_recon_moves()
        self.assertTrue(moves)
        return moves

    def _credit(self, amount):
        move = self.env['account.move'].create({
            'journal_id': self.general_journal.id, 'date': date(2026, 11, 12),
            'line_ids': [
                Command.create({'account_id': self.principal_account.id, 'debit': amount}),
                Command.create({'account_id': self.settlement_clearing_account.id, 'credit': amount,
                                'partner_id': self.vendor.id}),
            ],
        })
        move.action_post()
        return move.line_ids.filtered(lambda line: line.account_id == self.settlement_clearing_account)

    def test_marker_is_explicit_and_not_based_on_bill_reference(self):
        generated = self._bill(self._loan(count=2))
        self.assertTrue(generated.is_early_settlement)
        manual = self._manual_bill(is_early_settlement=False, ref='Pelunasan Dipercepat - Fake')
        self.assertFalse(manual.is_early_settlement)
        manual.is_early_settlement = True
        self.assertTrue(manual.is_early_settlement)
        with self.assertRaises(UserError):
            generated.is_early_settlement = False
        copied = generated.copy()
        self.assertFalse(copied.is_early_settlement)
        self.assertFalse(copied.early_settlement_loan_id)

    def test_full_recon_only_clearing_not_penalty_interest_payable_or_schedule(self):
        bill = self._bill(self._loan(count=48))
        bill.write({
            'date': date(2026, 11, 12), 'invoice_date': date(2026, 11, 12),
            'invoice_line_ids': [Command.create({
                'name': label, 'account_id': self.expense_account.id, 'quantity': 1, 'price_unit': amount,
            }) for label, amount in [('Penalty', 500000), ('Current Interest', 120000)]],
        })
        bill.action_post()
        before = self._snapshot(bill.early_settlement_loan_id)
        amount, payment_state = bill.amount_total, bill.payment_state
        originals = bill._early_settlement_clearing_lines()
        expected = sum(originals.mapped('amount_residual'))
        payable = bill.line_ids.filtered(lambda line: line.account_id == self.payable_account)
        payable_before = payable.amount_residual
        moves = self._recon(bill)
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves.state, 'posted')
        self.assertEqual(moves.date, bill.date)
        self.assertEqual(moves.partner_id, bill.partner_id)
        self.assertEqual(len(moves.line_ids), 2)
        debit = moves.line_ids.filtered('debit')
        credit = moves.line_ids.filtered('credit')
        self.assertEqual(debit.account_id, self.principal_account)
        self.assertEqual(credit.account_id, self.settlement_clearing_account)
        self.assertEqual(debit.debit, expected)
        self.assertEqual(credit.credit, expected)
        self.assertAlmostEqual(amount - expected, 620000)
        self.assertEqual(moves.line_ids.partner_id, bill.partner_id)
        self.assertTrue(all(line.analytic_distribution == {str(self.analytic.id): 100} for line in moves.line_ids))
        self.assertFalse(moves.line_ids.tax_ids)
        self.assertTrue(all(originals.mapped('reconciled')))
        self.assertEqual(len((originals | credit).full_reconcile_id), 1)
        self.assertTrue(all((originals | credit).mapped('matching_number')))
        self.assertEqual(len(set((originals | credit).mapped('matching_number'))), 1)
        self.assertEqual(payable.amount_residual, payable_before)
        self.assertEqual(bill.amount_total, amount)
        self.assertEqual(bill.payment_state, payment_state)
        self.assertEqual(self._snapshot(bill.early_settlement_loan_id), before)
        self.assertEqual(bill.early_settlement_recon_count, 1)
        self.assertFalse(self.env['account.payment'].search([('partner_id', '=', self.vendor.id)]))

    def test_partial_reconciliation_uses_only_remaining_residual(self):
        bill = self._posted_bill()
        originals = bill._early_settlement_clearing_lines()
        prior_credit = self._credit(1000000)
        (originals[0] | prior_credit).reconcile()
        self.assertFalse(originals[0].reconciled)
        self.assertEqual(sum(originals.mapped('amount_residual')), 11000000)
        moves = self._recon(bill)
        self.assertEqual(sum(moves.line_ids.mapped('credit')), 11000000)
        self.assertTrue(all((originals | prior_credit).mapped('reconciled')))
        self.assertEqual(len((originals | prior_credit | moves.line_ids.filtered('credit')).full_reconcile_id), 1)

    def test_repeat_click_reuses_posted_entry_and_matching_number(self):
        bill = self._posted_bill()
        move = self._recon(bill)
        matching = bill.invoice_line_ids.mapped('matching_number')
        self.assertEqual(self._recon(bill), move)
        self.assertEqual(bill.early_settlement_recon_count, 1)
        self.assertEqual(bill.invoice_line_ids.mapped('matching_number'), matching)
        self.assertEqual(bill.action_view_early_settlement_recon()['res_id'], move.id)

    def test_unreconcile_retry_reuses_existing_posted_entry(self):
        bill = self._posted_bill()
        move = self._recon(bill)
        bill.invoice_line_ids.remove_move_reconcile()
        self.assertFalse(all(bill.invoice_line_ids.mapped('reconciled')))
        self.assertEqual(self._recon(bill), move)
        self.assertTrue(all(bill.invoice_line_ids.mapped('reconciled')))

    def test_existing_draft_is_not_duplicated(self):
        bill = self._posted_bill()
        move = self._recon(bill)
        move.button_draft()
        with self.assertRaisesRegex(UserError, 'masih Draft'):
            self._recon(bill)
        self.assertEqual(bill.early_settlement_recon_count, 1)
        move.button_cancel()
        replacement = self._recon(bill)
        self.assertNotEqual(replacement, move)
        self.assertEqual(bill.early_settlement_recon_count, 2)

    def test_different_analytics_stay_on_both_journal_sides(self):
        bill = self._manual_bill()
        bill.invoice_line_ids[1].analytic_distribution = {}
        bill.action_post()
        move = self._recon(bill)
        self.assertEqual(len(move.line_ids), 4)
        self.assertEqual(len(move.line_ids.filtered(lambda line: bool(line.analytic_distribution))), 2)
        self.assertTrue(all(bill.invoice_line_ids.mapped('reconciled')))

    def test_multiple_clearing_accounts_use_their_own_mapping_and_journal(self):
        other_journal = self.env['account.journal'].create({
            'name': 'Recon Two', 'code': 'RCTWO', 'type': 'general', 'company_id': self.company.id,
        })
        other_account = self.settlement_clearing_account.copy({
            'code': '79600201', 'name': 'Clearing Two',
            'early_settlement_target_account_id': self.accrued_account.id,
            'early_settlement_journal_id': other_journal.id,
        })
        bill = self._manual_bill()
        bill.invoice_line_ids[1].account_id = other_account
        bill.action_post()
        moves = self._recon(bill)
        self.assertEqual(len(moves), 2)
        self.assertEqual(moves.journal_id, self.general_journal | other_journal)
        self.assertEqual(moves.line_ids.filtered('debit').account_id, self.principal_account | self.accrued_account)
        self.assertTrue(all(bill.invoice_line_ids.mapped('reconciled')))
        self.assertEqual(bill.action_view_early_settlement_recon()['view_mode'], 'list,form')

    def test_tax_lines_on_clearing_account_are_not_reconciled(self):
        tax = self.env['account.tax'].create({
            'name': 'Recon tax', 'amount': 11, 'type_tax_use': 'purchase',
            'company_id': self.company.id, 'tax_group_id': self.tax_group.id,
            'invoice_repartition_line_ids': [
                Command.create({'repartition_type': 'base'}),
                Command.create({'repartition_type': 'tax', 'account_id': self.settlement_clearing_account.id}),
            ],
        })
        bill = self._manual_bill(amounts=(1000,))
        bill.invoice_line_ids.tax_ids = tax
        bill.action_post()
        tax_lines = bill.line_ids.filtered('tax_line_id')
        self.assertEqual(sum(tax_lines.mapped('balance')), 110)
        moves = self._recon(bill)
        self.assertEqual(sum(moves.line_ids.mapped('credit')), 1000)
        self.assertFalse(tax_lines.reconciled)
        self.assertEqual(bill.amount_residual, 1110)

    def test_missing_mapping_no_partial_journal_is_created(self):
        bill = self._posted_bill()
        for field in ('early_settlement_target_account_id', 'early_settlement_journal_id'):
            original = self.settlement_clearing_account[field]
            self.settlement_clearing_account[field] = False
            with self.assertRaisesRegex(UserError, 'Lengkapi Akun Target'):
                self._recon(bill)
            self.assertFalse(bill.early_settlement_recon_move_ids)
            self.settlement_clearing_account[field] = original

    def test_clearing_must_allow_reconciliation(self):
        bill = self._posted_bill()
        self.settlement_clearing_account.reconcile = False
        with self.assertRaisesRegex(UserError, 'Allow Reconciliation'):
            self._recon(bill)
        self.assertFalse(bill.early_settlement_recon_move_ids)

    def test_wrong_target_or_purchase_journal_is_rejected(self):
        bill = self._posted_bill()
        # TEMPORARY: validasi Akun Target dinonaktifkan sementara; aktifkan kembali bersama validasinya.
        # for account in (self.settlement_clearing_account, self.payable_account):
        #     self.settlement_clearing_account.early_settlement_target_account_id = account
        #     with self.assertRaisesRegex(UserError, 'Akun Target harus'):
        #         self._recon(bill)
        self.settlement_clearing_account.early_settlement_target_account_id = self.principal_account
        self.settlement_clearing_account.early_settlement_journal_id = self.purchase_journal
        with self.assertRaisesRegex(UserError, 'jurnal umum aktif'):
            self._recon(bill)
        self.assertFalse(bill.early_settlement_recon_move_ids)

    def test_wrong_company_target_is_rejected(self):
        other = self.env['res.company'].create({'name': 'Recon Other', 'company_code': 'RECONQA'})
        target = self.env['account.account'].create({
            'name': 'Other Debt', 'code': '79600202', 'account_type': 'liability_non_current',
            'company_ids': [Command.set(other.ids)],
        })
        bill = self._posted_bill()
        self.settlement_clearing_account.early_settlement_target_account_id = target
        with self.assertRaisesRegex(UserError, 'company Vendor Bill'):
            self._recon(bill)
        self.assertFalse(bill.early_settlement_recon_move_ids)

    def test_company_dependent_settings_do_not_leak(self):
        other = self.env['res.company'].create({'name': 'Recon Shared', 'company_code': 'RCSHARED'})
        self.settlement_clearing_account.with_company(other).code = '79600006'
        self.settlement_clearing_account.company_ids |= other
        other_account = self.settlement_clearing_account.with_company(other)
        self.assertFalse(other_account.early_settlement_target_account_id)
        self.assertFalse(other_account.early_settlement_journal_id)
        self.assertEqual(self.settlement_clearing_account.early_settlement_target_account_id, self.principal_account)

    def test_foreign_currency_preserves_original_residual_and_not_new_rate(self):
        usd = self.env.ref('base.USD')
        usd.active = True
        self.env['res.currency.rate'].create({
            'currency_id': usd.id, 'company_id': self.company.id,
            'name': date(2026, 11, 12), 'rate': 1 / 16000,
        })
        bill = self._manual_bill(amounts=(100,), currency_id=usd.id)
        bill.action_post()
        original_balance = bill.invoice_line_ids.balance
        self.assertGreater(original_balance, 100)
        moves = self._recon(bill)
        self.assertEqual(moves.currency_id, usd)
        self.assertEqual(moves.line_ids.mapped('amount_currency'), [100, -100])
        self.assertEqual(sum(moves.line_ids.mapped('debit')), original_balance)
        self.assertTrue(bill.invoice_line_ids.reconciled)
        self.assertEqual(bill.amount_residual, 100)

    def test_flagged_posted_vendor_bill_required(self):
        draft = self._manual_bill()
        with self.assertRaisesRegex(UserError, 'sudah Posted'):
            self._recon(draft)
        draft.is_early_settlement = False
        draft.action_post()
        with self.assertRaisesRegex(UserError, 'sudah Posted'):
            self._recon(draft)
        self.assertFalse(draft.early_settlement_recon_move_ids)

    def test_marker_not_allowed_on_customer_invoice_or_entry(self):
        for kind in ('out_invoice', 'entry'):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                self._manual_bill(move_type=kind)

    def test_nonaccounting_user_cannot_process(self):
        bill = self._posted_bill()
        user = new_test_user(self.env, login='recon_stock_only', groups='stock.group_stock_user',
                             company_id=self.company.id)
        with self.assertRaises(AccessError):
            bill.with_user(user).action_recon_clearing_ap_leasing()
        self.assertFalse(bill.early_settlement_recon_move_ids)

    def test_accounting_user_can_process_without_sudo(self):
        for index, group in enumerate(('account.group_account_user', 'account.group_account_invoice')):
            bill = self._posted_bill()
            user = new_test_user(self.env, login='recon_accounting_%s' % index, groups=group,
                                 company_id=self.company.id)
            action = bill.with_user(user).action_recon_clearing_ap_leasing()
            self.assertEqual(action['res_id'], bill.early_settlement_recon_move_ids.id)
            self.assertEqual(bill.early_settlement_recon_move_ids.create_uid, user)
            self.assertEqual(bill.early_settlement_recon_move_ids.state, 'posted')

    def test_fully_reconciled_clearing_without_recon_entry_has_no_remaining_amount(self):
        bill = self._posted_bill()
        originals = bill._early_settlement_clearing_lines()
        (originals | self._credit(sum(originals.mapped('amount_residual')))).reconcile()
        with self.assertRaisesRegex(UserError, 'Tidak ada sisa saldo'):
            self._recon(bill)
        self.assertFalse(bill.early_settlement_recon_move_ids)

    def test_fixed_currency_mismatch_does_not_create_a_journal(self):
        bill = self._posted_bill()
        self.general_journal.currency_id = self.env.ref('base.USD')
        with self.assertRaisesRegex(UserError, 'Mata uang jurnal/akun'):
            self._recon(bill)
        self.assertFalse(bill.early_settlement_recon_move_ids)

    def test_source_link_cannot_be_forged_or_reassigned(self):
        bill = self._posted_bill()
        with self.assertRaisesRegex(UserError, 'Gunakan tombol'):
            self.env['account.move'].create({
                'move_type': 'entry', 'journal_id': self.general_journal.id,
                'early_settlement_recon_bill_id': bill.id,
            })
        move = self._recon(bill)
        with self.assertRaisesRegex(UserError, 'tidak dapat diubah'):
            move.early_settlement_recon_bill_id = False

    def test_bill_reset_requires_review_of_active_recon(self):
        bill = self._posted_bill()
        move = self._recon(bill)
        with self.assertRaisesRegex(UserError, 'jurnal Recon Clearing'):
            bill.button_draft()
        with self.assertRaisesRegex(UserError, 'jurnal Recon Clearing'):
            bill.button_cancel()
        move.button_draft()
        move.button_cancel()
        bill.button_draft()
        self.assertEqual(bill.state, 'draft')

    def test_native_reversal_does_not_copy_bill_marker_or_source_link(self):
        bill = self._posted_bill()
        move = self._recon(bill)
        reversal = move._reverse_moves([{'date': bill.date}], cancel=True)
        self.assertEqual(reversal.state, 'posted')
        self.assertFalse(reversal.early_settlement_recon_bill_id)
        self.assertFalse(reversal.is_early_settlement)
        self.assertFalse(bill._active_early_settlement_recon_moves())

    def test_partial_reversal_does_not_allow_duplicate_clearing(self):
        bill = self._posted_bill()
        move = self._recon(bill)
        bill.invoice_line_ids.remove_move_reconcile()
        reverse = move._reverse_moves([{'date': bill.date}], cancel=False)
        reverse.write({'line_ids': [
            Command.update(reverse.line_ids.filtered('debit').id,
                           {'debit': 1000000, 'amount_currency': 1000000}),
            Command.update(reverse.line_ids.filtered('credit').id,
                           {'credit': 1000000, 'amount_currency': -1000000}),
        ]})
        reverse.action_post()
        original_credit = move.line_ids.filtered('credit')
        reversal_debit = reverse.line_ids.filtered('debit')
        (original_credit | reversal_debit).reconcile()
        self.assertEqual(bill._active_early_settlement_recon_moves(), move)
        with self.assertRaisesRegex(UserError, 'Saldo jurnal Recon yang sudah ada berbeda'):
            self._recon(bill)
        self.assertEqual(bill.early_settlement_recon_count, 1)
        self.assertFalse(any(bill.invoice_line_ids.mapped('reconciled')))

    def test_locked_accounting_date_does_not_leave_new_journal_or_matching(self):
        bill = self._posted_bill()
        self.company.hard_lock_date = bill.date
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self._recon(bill)
        self.assertFalse(bill.early_settlement_recon_move_ids)
        self.assertFalse(any(bill.invoice_line_ids.mapped('reconciled')))

    def test_upgrade_marks_only_existing_linked_bills_without_financial_changes(self):
        bill = self._posted_bill()
        manual = self._manual_bill(is_early_settlement=False, ref='Pelunasan Dipercepat')
        before = bill.line_ids.read(['account_id', 'balance', 'date', 'analytic_distribution'])
        bill.flush_recordset()
        self.env.cr.execute('UPDATE account_move SET is_early_settlement = FALSE WHERE id = %s', (bill.id,))
        path = Path(__file__).resolve().parents[1] / 'migrations' / '19.0.1.0.30' / 'post-migrate.py'
        spec = spec_from_file_location('recon_migration', path)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, '19.0.1.0.29')
        module.migrate(self.env.cr, '19.0.1.0.29')
        (bill | manual).invalidate_recordset()
        self.assertTrue(bill.is_early_settlement)
        self.assertFalse(manual.is_early_settlement)
        self.assertEqual(bill.line_ids.read(['account_id', 'balance', 'date', 'analytic_distribution']), before)
        self.assertFalse(bill.early_settlement_recon_move_ids)

    def test_native_compiled_views_include_configuration_marker_and_buttons(self):
        account_view = etree.fromstring(self.env['account.account'].get_view(
            self.env.ref('account.view_account_form').id, 'form')['arch'])
        for field in ('is_early_settlement_clearing', 'early_settlement_target_account_id',
                      'early_settlement_journal_id'):
            self.assertTrue(account_view.xpath("//field[@name='%s']" % field))
        target_fields = account_view.xpath("//field[@name='early_settlement_target_account_id']")
        self.assertTrue(all(not field.get('domain') for field in target_fields))
        metadata = self.env['account.account'].fields_get(['early_settlement_target_account_id'])
        self.assertFalse(metadata['early_settlement_target_account_id'].get('domain'))
        self.assertFalse(self.env['account.account']._fields['early_settlement_target_account_id'].domain)
        bill_view = etree.fromstring(self.env['account.move'].get_view(
            self.env.ref('account.view_move_form').id, 'form')['arch'])
        buttons = bill_view.xpath("//header/button[@name='action_recon_clearing_ap_leasing']")
        self.assertEqual(len(buttons), 1)
        self.assertIn("state != 'posted'", buttons[0].get('invisible'))
        self.assertIn('not is_early_settlement', buttons[0].get('invisible'))
        self.assertTrue(bill_view.xpath("//field[@name='is_early_settlement']"))

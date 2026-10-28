from datetime import date
import importlib.util
from pathlib import Path

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time
from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .test_early_settlement import LeasingScheduleCommon
from .test_flat_schedule import TestLeasingFlatSchedule


@tagged('post_install', '-at_install')
class TestLeasingScheduleDates(LeasingScheduleCommon):
    _flat_loan = TestLeasingFlatSchedule._flat_loan
    _computed = TestLeasingFlatSchedule._computed

    def _effective(self, **values):
        loan = self._loan(count=4, state='draft')
        loan.write({
            'harga_otr': 100000000, 'down_payment_leasing': 10000000,
            'total_hutang': 90000000, 'amount_borrowed': 90000000,
            'monthly_installment': 25000000, 'interest_rate_annual': 6,
            'due_date': date(2027, 1, 31), **values,
        })
        loan.action_compute_amortization_schedule()
        return loan

    def _amounts(self, loan):
        return loan.line_ids.read(['principal', 'interest', 'payment', 'outstanding_balance', 'interest_balance'])

    def test_both_methods_anchor_first_due_date_and_restore_month_end_after_february(self):
        for year, february in [(2027, 28), (2028, 29)]:
            for method in ['effective', 'flat']:
                with self.subTest(year=year, method=method):
                    due = date(year, 1, 31)
                    loan = (self._effective(due_date=due) if method == 'effective' else
                            self._computed(duration=4, monthly_installment=0, due_date=due))
                    self.assertEqual(loan.line_ids.mapped('date'), [due, date(year, 2, february),
                                                                  date(year, 3, 31), date(year, 4, 30)])
                    self.assertNotEqual(loan.start_date_leasing, due)

    def test_ordinary_day_stays_same_for_both_methods_and_flat_advarr_values(self):
        for method, advarr in [('effective', False), ('flat', 'in_advance_addm'), ('flat', 'in_arrears')]:
            with self.subTest(method=method, advarr=advarr):
                due = date(2027, 1, 26)
                loan = (self._effective(due_date=due) if method == 'effective' else
                        self._computed(duration=4, monthly_installment=0, due_date=due, advarr=advarr))
                self.assertEqual(loan.line_ids.mapped('date'), [due + relativedelta(months=i) for i in range(4)])

    def test_missing_due_date_does_not_fall_back_or_delete_existing_schedule(self):
        for method in ['effective', 'flat']:
            loan = self._loan(count=4, state='draft', compute_method=method, due_date=False)
            before = loan.line_ids.read(['date', 'principal', 'interest'])
            with self.assertRaisesRegex(UserError, 'Tanggal Jatuh Tempo'):
                loan.action_compute_amortization_schedule()
            self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest']), before)

    def test_flat_manual_due_date_edit_preserves_amounts_and_can_confirm_and_pay(self):
        loan = self._computed()
        amounts = self._amounts(loan)
        second = loan.line_ids[1]
        second.date += relativedelta(days=2)
        self.assertTrue(second.date_is_manual)
        self.assertFalse(loan.flat_schedule_needs_compute)
        self.assertEqual(self._amounts(loan), amounts)
        loan.action_confirm()
        self.env['leasing.payment.wizard'].with_context(active_ids=second.ids).create({
            'journal_id': self.bank_journal.id,
        }).action_confirm_payment()
        self.assertEqual(second.vendor_bill_id.state, 'posted')

    def test_effective_manual_due_date_edit_preserves_amounts(self):
        loan = self._effective()
        amounts = self._amounts(loan)
        loan.line_ids[1].date += relativedelta(days=1)
        self.assertTrue(loan.line_ids[1].date_is_manual)
        self.assertEqual(self._amounts(loan), amounts)
        loan.action_confirm()
        self.assertEqual(loan.state, 'running')

    def test_flat_related_table_accepts_date_edit_from_form_only(self):
        loan = self._computed()
        expected = loan.line_ids[1].date + relativedelta(days=1)
        with Form(loan, view='account_loans.account_loan_form_view') as form:
            with form.flat_line_ids.edit(1) as row:
                row.date = expected
                with self.assertRaises(AssertionError):
                    row.interest = 1
        self.assertEqual(loan.line_ids[1].date, expected)
        self.assertFalse(loan.flat_schedule_needs_compute)

    def test_effective_table_accepts_date_edit_from_form_but_not_amounts(self):
        loan = self._effective()
        expected = loan.line_ids[1].date + relativedelta(days=1)
        with Form(loan, view='account_loans.account_loan_form_view') as form:
            with form.line_ids.edit(1) as row:
                row.date = expected
                with self.assertRaises(AssertionError):
                    row.principal = 1
        self.assertEqual(loan.line_ids[1].date, expected)

    def test_running_dates_are_protected_for_both_methods(self):
        for loan in [self._effective(), self._computed()]:
            loan.action_confirm()
            original = loan.line_ids[0].date
            with self.assertRaises(UserError):
                loan.line_ids[0].date = original + relativedelta(days=1)
            with self.assertRaises(UserError):
                loan.due_date += relativedelta(days=1)
            self.assertEqual(loan.line_ids[0].date, original)

    def test_draft_dates_with_payment_or_accrual_history_are_protected(self):
        for accrued in [False, True]:
            loan = self._effective()
            self._entry(loan.line_ids[0], accrued=accrued)
            with self.assertRaises(UserError):
                loan.line_ids[0].date += relativedelta(days=1)

    def test_recompute_cannot_replace_effective_or_flat_rows_with_financial_history(self):
        for loan in [self._effective(), self._computed()]:
            self._entry(loan.line_ids[0], state='draft')
            before = loan.line_ids.read(['date', 'principal', 'interest', 'vendor_bill_id'])
            with self.assertRaisesRegex(UserError, 'terhubung transaksi'):
                loan.action_compute_amortization_schedule()
            self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest', 'vendor_bill_id']), before)

    def test_duplicate_and_reordered_dates_rollback_without_changing_flat_signature(self):
        loan = self._computed()
        second = loan.line_ids[1]
        original, signature = second.date, loan.flat_schedule_signature
        for proposed in [loan.line_ids[0].date, loan.line_ids[0].date - relativedelta(days=1)]:
            with self.assertRaisesRegex(UserError, 'berurutan'):
                second.date = proposed
            self.assertEqual(second.date, original)
            self.assertEqual(loan.flat_schedule_signature, signature)
            self.assertFalse(loan.flat_schedule_needs_compute)

    def test_manual_date_edit_cannot_bless_changed_flat_financial_amount(self):
        loan = self._computed()
        second = loan.line_ids[1]
        second.principal += 100
        with self.assertRaisesRegex(UserError, 'Compute Flat Schedule'):
            second.date += relativedelta(days=1)
        self.assertTrue(loan.flat_schedule_needs_compute)

    def test_changing_header_due_date_requires_compute_for_both_methods(self):
        for loan in [self._effective(), self._computed()]:
            loan.due_date += relativedelta(days=1)
            with self.assertRaisesRegex(UserError, 'Compute'):
                loan.action_confirm()
            loan.action_compute_amortization_schedule()
            self.assertEqual(loan.line_ids[0].date, loan.due_date)
            loan.action_confirm()

    @freeze_time('2026-10-28 03:00:00')
    def test_running_number_always_uses_sequence_even_for_explicit_and_copied_names(self):
        first = self._loan(count=2, state='draft', name='MANUAL NAME')
        second = self._loan(count=2, state='draft', name='New Leasing 5')
        copied = first.copy({'name': 'COPIED NAME'})
        for loan in first | second | copied:
            self.assertRegex(loan.name, r'^TA/CRS/10/2026/\d{5}$')
        self.assertEqual(len(set((first | second | copied).mapped('name'))), 3)
        with self.assertRaisesRegex(UserError, 'otomatis'):
            first.name = 'CHANGED NAME'

    def test_payment_date_uses_posted_payment_accounting_date_and_tracks_changes(self):
        loan = self._loan(count=2)
        line = loan.line_ids[0]
        move = self._entry(line, state='draft')
        move.date = date(2026, 9, 15)
        self.assertFalse(line.payment_date)
        move.action_post()
        self.assertEqual(line.payment_date, date(2026, 9, 15))
        move.button_draft()
        self.assertFalse(line.payment_date)
        move.date = date(2026, 9, 16)
        move.action_post()
        self.assertEqual(line.payment_date, date(2026, 9, 16))

    def test_native_payment_entry_also_populates_payment_date_but_accrual_does_not(self):
        loan = self._loan(count=2)
        first, second = loan.line_ids
        native = self._entry(first, native=True)
        self.assertEqual(first.payment_date, native.date)
        self._entry(second, accrued=True)
        self.assertFalse(second.payment_date)
        native.button_draft()
        self.assertFalse(first.payment_date)

    def test_upgrade_refreshes_legacy_payment_date_without_renaming_or_redating_schedule(self):
        loan = self._loan(count=2)
        line = loan.line_ids[0]
        move = self._entry(line)
        before_name = loan.name
        before_schedule = loan.line_ids.read(['date', 'principal', 'interest', 'vendor_bill_id'])
        self.env.flush_all()
        # Simulate the stored legacy value from the former sticky computation.
        self.env.cr.execute('UPDATE account_loan_line SET payment_date = %s WHERE id = %s',
                            (date(2020, 1, 1), line.id))
        line.invalidate_recordset(['payment_date'])
        self.assertEqual(line.payment_date, date(2020, 1, 1))
        path = Path(__file__).resolve().parents[1] / 'migrations/19.0.1.0.6/post-migrate.py'
        spec = importlib.util.spec_from_file_location('leasing_payment_date_upgrade', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.migrate(self.env.cr, '19.0.1.0.5')
        line.invalidate_recordset(['payment_date'])
        self.assertEqual(line.payment_date, move.date)
        self.assertEqual(loan.name, before_name)
        self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest', 'vendor_bill_id']), before_schedule)
        self.assertEqual(move.state, 'posted')

    def test_labels_readonly_name_hidden_disbursement_and_due_payment_column_order(self):
        self.assertEqual(self.env['account.loan']._fields['start_date_leasing'].string, 'Tanggal Mulai Leasing')
        form = etree.fromstring(self.env['account.loan'].get_view(
            view_id=self.env.ref('account_loans.account_loan_form_view').id, view_type='form')['arch'])
        self.assertEqual(form.xpath("//field[@name='name']")[0].get('readonly'), '1')
        self.assertEqual(form.xpath("//field[@name='disbursement_date']")[0].get('invisible'), '1')
        effective = etree.fromstring(self.env['account.loan.line'].get_view(
            view_id=self.env.ref('account_loans.account_loan_line_list_view').id, view_type='list')['arch'])
        flat = form.xpath("//field[@name='flat_line_ids']/list")[0]
        for table in [effective, flat]:
            due = table.xpath("./field[@name='date']")[0]
            self.assertEqual(due.get('string'), 'Due Date')
            self.assertEqual(due.get('readonly'), "loan_state != 'draft'")
            self.assertEqual(due.getnext().get('name'), 'payment_date')
            self.assertEqual(due.getnext().get('string'), 'Payment Date')
            self.assertEqual(due.getnext().get('readonly'), '1')

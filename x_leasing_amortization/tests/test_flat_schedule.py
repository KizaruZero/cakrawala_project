from datetime import date

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time
from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from ..lib.flat_schedule import FlatScheduleError, build_flat_schedule
from ..models.account_loan import AccountLoan as OriginalLoan
from ..models.account_loan_compute_wizard import AccountLoanComputeWizard as OriginalWizard
from .test_early_settlement import LeasingScheduleCommon


# Legacy equivalent-allocation data retained only for upgrade regression tests.
# New Flat calculations must NOT use this allocation.
# (principal, interest, remaining principal, remaining interest)
LEGACY_EQUIVALENT_ROWS = [
    (25353000, 0, 762147000, 125208000),
    (18722011, 6630989, 743424989, 118577011),
    (18884900, 6468100, 724540089, 112108911),
    (19049206, 6303794, 705490883, 105805117),
    (19214942, 6138058, 686275941, 99667059),
    (19382120, 5970880, 666893821, 93696179),
    (19550752, 5802248, 647343069, 87893931),
    (19720852, 5632148, 627622217, 82261783),
    (19892431, 5460569, 607729786, 76801214),
    (20065504, 5287496, 587664282, 71513718),
    (20240082, 5112918, 567424200, 66400800),
    (20416179, 4936821, 547008021, 61463979),
    (20593808, 4759192, 526414213, 56704787),
    (20772982, 4580018, 505641231, 52124769),
    (20953716, 4399284, 484687515, 47725485),
    (21136021, 4216979, 463551494, 43508506),
    (21319913, 4033087, 442231581, 39475419),
    (21505405, 3847595, 420726176, 35627824),
    (21692511, 3660489, 399033665, 31967335),
    (21881245, 3471755, 377152420, 28495580),
    (22071620, 3281380, 355080800, 25214200),
    (22263653, 3089347, 332817147, 22124853),
    (22457355, 2895645, 310359792, 19229208),
    (22652744, 2700256, 287707048, 16528952),
    (22849832, 2503168, 264857216, 14025784),
    (23048634, 2304366, 241808582, 11721418),
    (23249167, 2103833, 218559415, 9617585),
    (23451444, 1901556, 195107971, 7716029),
    (23655481, 1697519, 171452490, 6018510),
    (23861294, 1491706, 147591196, 4526804),
    (24068897, 1284103, 123522299, 3242701),
    (24278306, 1074694, 99243993, 2168007),
    (24489537, 863463, 74754456, 1304544),
    (24702606, 650394, 50051850, 654150),
    (24917529, 435471, 25134321, 218679),
    (25134321, 218679, 0, 0),
]


@tagged('post_install', '-at_install')
class TestLeasingFlatSchedule(LeasingScheduleCommon):

    def _flat_loan(self, **overrides):
        count = overrides.pop('duration', 36)
        loan = self._loan(count=max(count, 1), state='draft', compute_method='flat')
        loan.write({
            'harga_otr': 875000000, 'down_payment_leasing': 87500000,
            'total_hutang': 787500000, 'amount_borrowed': 787500000,
            'monthly_installment': 25353000, 'interest_rate_annual': 5.3,
            'duration': count, 'advarr': 'in_advance_addm',
            'start_date_leasing': date(2025, 11, 14), 'date': date(2025, 11, 14),
            **overrides,
        })
        return loan

    def _computed(self, **overrides):
        loan = self._flat_loan(**overrides)
        loan.action_compute_amortization_schedule()
        return loan

    def _financial_rows(self, loan):
        return [(line.date, line.principal, line.interest, line.payment,
                 line.outstanding_balance, line.interest_balance)
                for line in loan.line_ids.sorted(lambda item: (item.date, item.id))]

    def _legacy_flat_loan(self, state='draft'):
        loan = self._flat_loan()
        loan.line_ids.unlink()
        loan.write({
            'line_ids': [Command.create({
                'date': date(2025, 11, 14) + relativedelta(months=index),
                'principal': values[0], 'interest': values[1],
            }) for index, values in enumerate(LEGACY_EQUIVALENT_ROWS)],
            'interest': 125208000, 'schedule_compute_method': 'flat',
            'flat_schedule_version': False,
        })
        loan.flat_schedule_signature = loan._flat_fingerprint()
        if state == 'running':
            # Fixture simulates a Running v0.3 record that predates this upgrade;
            # the new Confirm action must never accept the old Draft formula.
            self.env.flush_all()
            self.env.cr.execute("UPDATE account_loan SET state = 'running' WHERE id = %s", (loan.id,))
            loan.invalidate_recordset()
        return loan

    def test_legacy_flat_draft_requires_explicit_recompute_without_auto_rewrite(self):
        loan = self._legacy_flat_loan()
        before = self._financial_rows(loan)
        self.assertTrue(loan.flat_schedule_needs_compute)
        with self.assertRaisesRegex(UserError, 'Compute Flat Schedule'):
            loan.action_confirm()
        self.assertEqual(self._financial_rows(loan), before)
        loan.action_compute_amortization_schedule()
        self.assertEqual(loan.flat_schedule_version, 'constant_v2')
        self.assertEqual(loan.line_ids[1].interest, 3577371)

    def test_legacy_running_flat_keeps_old_allocation_and_transaction_flow(self):
        loan = self._legacy_flat_loan(state='running')
        before = self._financial_rows(loan)
        self.assertFalse(loan.flat_schedule_needs_compute)
        loan._validate_flat_schedule()
        self.assertEqual(loan.line_ids[0].flat_display_principal, 25353000)
        self.env['leasing.payment.wizard'].with_context(active_ids=loan.line_ids[:1].ids).create({
            'journal_id': self.bank_journal.id,
        }).action_confirm_payment()
        self.assertEqual(loan.line_ids[0].vendor_bill_id.state, 'posted')
        self.assertEqual(self._bill(loan).amount_total, 762147000)
        self.assertEqual(self._financial_rows(loan), before)
        self.assertFalse(loan.flat_schedule_version)
        with self.assertRaises(UserError):
            loan.action_compute_amortization_schedule()

    def test_all_36_rows_follow_constant_allocations_and_anniversary_dates(self):
        loan = self._computed()
        self.assertEqual(len(loan.flat_line_ids), 36)
        self.assertEqual(loan.flat_line_ids, loan.line_ids)
        principal_balance, interest_balance = 787500000, 125208000
        for index, line in enumerate(loan.flat_line_ids):
            with self.subTest(installment=index + 1):
                principal = 25353000 if index == 0 else 21775614 if index == 35 else 21775629
                interest = 0 if index == 0 else 3577386 if index == 35 else 3577371
                principal_balance -= principal
                interest_balance -= interest
                self.assertEqual(line.installment_number, index + 1)
                self.assertEqual(line.date, date(2025, 11, 14) + relativedelta(months=index))
                self.assertEqual((line.principal, line.interest, line.outstanding_balance,
                                  line.interest_balance), (principal, interest, principal_balance, interest_balance))
                self.assertEqual(line.flat_display_principal, principal if index else 0)
                self.assertEqual(line.payment, 25353000)
                self.assertFalse(line.payment_date)
        self.assertEqual(sum(loan.line_ids.mapped('principal')), 787500000)
        self.assertEqual(sum(loan.line_ids.mapped('interest')), 125208000)
        self.assertEqual(loan.flat_effective_rate_annual, 0)
        self.assertEqual(loan.flat_schedule_version, 'constant_v2')
        self.assertAlmostEqual(loan.flat_implied_rate_annual, 5.2998095238095, places=9)
        self.assertFalse(loan.flat_schedule_needs_compute)
        self.env.invalidate_all()
        self.assertFalse(loan.flat_schedule_needs_compute)
        self.assertEqual(loan.flat_line_ids[1].interest, 3577371)
        self.assertEqual(loan.flat_line_ids[0].flat_display_principal, 0)

    def test_flat_header_totals_include_first_installment_and_preserve_effective_semantics(self):
        loan = self._computed()
        self.assertEqual(loan.total_installment_payment, 912708000)
        self.assertEqual(loan.saldo_pokok_hutang, 787500000)
        self.assertEqual(loan.total_bunga, 125208000)
        self.assertEqual(loan.interest, 125208000)
        self.assertEqual(loan.amount_borrowed_difference, 0)
        self.assertEqual(loan.interest_difference, 0)
        self.assertEqual(loan.duration_difference, 0)

    def test_contract_installment_wins_even_if_quoted_flat_rate_changes(self):
        loan = self._computed(interest_rate_annual=6)
        self.assertEqual(loan.monthly_installment, 25353000)
        self.assertEqual(loan.line_ids[1].interest, 3577371)
        self.assertEqual(loan.interest_rate_annual, 6)

    def test_empty_installment_uses_flat_formula_not_rounded_to_thousands(self):
        loan = self._computed(monthly_installment=0)
        self.assertEqual(loan.monthly_installment, 25353125)
        self.assertEqual(loan.flat_last_auto_installment, 25353125)
        self.assertEqual(loan.total_installment_payment, 912712500)
        self.assertEqual(loan.total_bunga, 125212500)
        self.assertEqual(loan.line_ids[-1].outstanding_balance, 0)

    def test_auto_installment_refreshes_when_rate_changes_and_manual_override_wins(self):
        loan = self._computed(monthly_installment=0)
        loan.interest_rate_annual = 6
        self.assertTrue(loan.flat_schedule_needs_compute)
        loan.action_compute_amortization_schedule()
        self.assertEqual(loan.monthly_installment, 25812500)
        loan.monthly_installment = 25353000
        loan.action_compute_amortization_schedule()
        self.assertEqual(loan.monthly_installment, 25353000)
        self.assertEqual(loan.flat_last_auto_installment, 0)

    def test_explicit_same_installment_can_be_locked_as_contract(self):
        loan = self._computed(monthly_installment=0)
        self.assertEqual(loan.flat_installment_source, 'automatic')
        contract_amount = loan.monthly_installment
        loan.write({'monthly_installment': contract_amount, 'interest_rate_annual': 6})
        self.assertEqual(loan.flat_installment_source, 'contract')
        loan.action_compute_amortization_schedule()
        self.assertEqual(loan.monthly_installment, contract_amount)
        self.assertEqual(loan.flat_last_auto_installment, 0)

    def test_arrears_also_has_zero_first_interest_but_starts_next_month(self):
        loan = self._computed(advarr='in_arrears')
        self.assertEqual(loan.line_ids[0].date, date(2025, 12, 14))
        self.assertEqual(loan.line_ids[0].interest, 0)
        self.assertEqual(loan.line_ids[0].flat_display_principal, 0)
        self.assertEqual(loan.line_ids[0].outstanding_balance, 762147000)
        self.assertEqual(loan.line_ids[1].principal, 21775629)
        self.assertEqual(loan.line_ids[1].interest, 3577371)
        self.assertEqual(loan.line_ids[-1].date, date(2028, 11, 14))
        self.assertEqual(loan.flat_effective_rate_annual, 0)
        self.assertEqual(loan.total_bunga, 125208000)
        self.assertEqual(loan.line_ids[-1].interest_balance, 0)

    def test_month_end_dates_do_not_drift_and_explicit_eom_is_supported(self):
        loan = self._computed(duration=4, monthly_installment=0,
                              start_date_leasing=date(2027, 1, 31), date=date(2027, 1, 31))
        self.assertEqual(loan.line_ids.mapped('date'), [date(2027, 1, 31), date(2027, 2, 28),
                                                      date(2027, 3, 31), date(2027, 4, 30)])
        loan.write({'start_date_leasing': date(2027, 1, 14), 'flat_payment_timing': 'end_of_month'})
        loan.action_compute_amortization_schedule()
        self.assertEqual(loan.line_ids.mapped('date'), [date(2027, 1, 14), date(2027, 2, 28),
                                                      date(2027, 3, 31), date(2027, 4, 30)])

    def test_zero_rate_currency_rounding_adjusts_final_principal_not_interest(self):
        loan = self._computed(harga_otr=100, down_payment_leasing=0, total_hutang=100,
                              amount_borrowed=100, duration=3, monthly_installment=0, interest_rate_annual=0)
        self.assertEqual(loan.line_ids.mapped('principal'), [33.33, 33.33, 33.34])
        self.assertEqual(loan.total_installment_payment, 100)
        self.assertEqual(loan.total_bunga, 0)
        self.assertEqual(loan.flat_effective_rate_annual, 0)

    def test_one_advance_installment_has_no_interest_or_extra_period(self):
        loan = self._computed(duration=1, monthly_installment=0)
        self.assertEqual(len(loan.line_ids), 1)
        self.assertEqual(loan.line_ids.principal, 787500000)
        self.assertEqual(loan.line_ids.interest, 0)
        self.assertEqual(loan.line_ids.outstanding_balance, 0)
        self.assertEqual(loan.line_ids.flat_display_principal, 0)

    def test_currency_precision_rounding_allocates_both_residuals_to_final_row(self):
        loan = self._computed(flat_interest_rounding='currency')
        for line in loan.line_ids[1:-1]:
            self.assertEqual(line.principal, 21775628.57)
            self.assertEqual(line.interest, 3577371.43)
            self.assertAlmostEqual(line.payment, 25353000, places=2)
        self.assertEqual(loan.line_ids[-1].principal, 21775628.62)
        self.assertEqual(loan.line_ids[-1].interest, 3577371.38)
        self.assertAlmostEqual(loan.line_ids[-1].outstanding_balance, 0, places=2)
        self.assertEqual(loan.line_ids[-1].interest_balance, 0)
        self.assertAlmostEqual(loan.total_bunga, 125208000, places=2)
        loan.action_confirm()
        self.assertFalse(loan.flat_schedule_needs_compute)

    def test_invalid_parameters_leave_existing_rows_untouched(self):
        cases = [
            {'advarr': False}, {'duration': 0}, {'monthly_installment': -1},
            {'monthly_installment': 1}, {'interest_rate_annual': -1},
            {'down_payment_leasing': -1}, {'down_payment_leasing': 875000000},
            {'start_date_leasing': False, 'date': False},
        ]
        for values in cases:
            with self.subTest(values=values):
                loan = self._flat_loan(**values)
                before, ids = self._financial_rows(loan), loan.line_ids.ids
                with self.assertRaises(UserError):
                    loan.action_compute_amortization_schedule()
                self.assertEqual(loan.line_ids.ids, ids)
                self.assertEqual(self._financial_rows(loan), before)

    def test_non_finite_inputs_are_rejected_by_shared_calculator(self):
        for key in ['principal', 'annual_flat_rate', 'installment']:
            args = {'principal': 1000, 'annual_flat_rate': 5, 'months': 12,
                    'start_date': date(2026, 1, 1), 'advance': True, key: float('nan')}
            with self.subTest(key=key), self.assertRaises(FlatScheduleError):
                build_flat_schedule(**args)

    def test_draft_recompute_replaces_only_unlinked_schedule(self):
        loan = self._computed()
        old_ids = loan.line_ids.ids
        loan.action_compute_amortization_schedule()
        self.assertFalse(self.env['account.loan.line'].browse(old_ids).exists())
        self.assertEqual(len(loan.flat_line_ids), 36)
        self.assertEqual(loan.flat_line_ids, loan.line_ids)

    def test_changed_parameters_require_recompute_before_confirm(self):
        loan = self._computed()
        loan.interest_rate_annual = 6
        with self.assertRaisesRegex(UserError, 'Compute Flat Schedule'):
            loan.action_confirm()
        self.assertEqual(loan.state, 'draft')
        loan.action_compute_amortization_schedule()
        loan.action_confirm()
        self.assertEqual(loan.state, 'running')

    def test_changed_line_and_forged_fingerprint_cannot_confirm_wrong_schedule(self):
        loan = self._computed()
        loan.line_ids[1].principal += 100
        with self.assertRaisesRegex(UserError, 'Compute Flat Schedule'):
            loan.action_confirm()
        loan.flat_schedule_signature = loan._flat_fingerprint()
        with self.assertRaisesRegex(UserError, 'perhitungan kontrak'):
            loan.action_confirm()

    def test_running_flat_parameters_amounts_reset_and_recompute_are_protected(self):
        loan = self._computed()
        loan.action_confirm()
        before = self._financial_rows(loan)
        for operation in [lambda: loan.write({'monthly_installment': 26000000}),
                          lambda: loan.line_ids[0].write({'principal': 1}),
                          lambda: loan.line_ids[0].unlink(), lambda: loan.action_reset(),
                          lambda: loan.action_compute_amortization_schedule()]:
            with self.assertRaises(UserError):
                operation()
        self.assertEqual(self._financial_rows(loan), before)

    def test_draft_with_any_payment_history_cannot_recompute_or_switch_method(self):
        loan = self._computed()
        self._entry(loan.line_ids[0], state='draft')
        before = self._financial_rows(loan)
        with self.assertRaisesRegex(UserError, 'terhubung transaksi'):
            loan.action_compute_amortization_schedule()
        with self.assertRaisesRegex(UserError, 'terhubung transaksi'):
            loan.compute_method = 'effective'
        self.assertEqual(self._financial_rows(loan), before)

    def test_switching_flat_to_effective_requires_effective_compute(self):
        loan = self._computed()
        loan.compute_method = 'effective'
        with self.assertRaisesRegex(UserError, 'Bunga Efektif'):
            loan.action_confirm()
        loan.action_compute_amortization_schedule()
        self.assertEqual(loan.schedule_compute_method, 'effective')
        loan.action_confirm()
        self.assertEqual(loan.state, 'running')

    def test_flat_payment_updates_same_canonical_rows_and_early_settlement_uses_tail(self):
        loan = self._computed()
        loan.action_confirm()
        self.env['leasing.payment.wizard'].with_context(active_ids=loan.flat_line_ids[:13].ids).create({
            'journal_id': self.bank_journal.id, 'payment_date': date(2026, 10, 27),
        }).action_confirm_payment()
        self.assertEqual(loan.flat_line_ids[:13].vendor_bill_id.state, 'posted')
        self.assertTrue(all(line.payment_date == date(2026, 10, 27) for line in loan.flat_line_ids[:13]))
        self.assertFalse(loan.flat_line_ids[13:].vendor_bill_id)
        self.assertEqual(loan.remaining_loan, 23)
        self.assertEqual(loan.outstanding_balance, 500839452)
        before = self._financial_rows(loan)
        bill = self._bill(loan)
        self.assertEqual(len(bill.invoice_line_ids), 23)
        self.assertEqual(bill.invoice_line_ids[0].price_unit, 21775629)
        self.assertEqual(bill.amount_total, 500839452)
        bill.action_post()
        self.assertEqual(loan.state, 'running')
        self.assertEqual(self._financial_rows(loan), before)

    @freeze_time('2026-01-15')
    def test_accrual_cron_uses_flat_interest_and_never_marks_payment_date(self):
        loan = self._computed()
        loan.action_confirm()
        self.env['account.loan.line']._cron_generate_interest_adjustment()
        self.assertFalse(loan.line_ids[0].monthly_adjustment_move_id)
        self.assertEqual(loan.line_ids[1].monthly_adjustment_move_id.amount_total, 3577371)
        self.assertEqual(loan.line_ids[2].monthly_adjustment_move_id.amount_total, 3577371)
        self.assertFalse(loan.line_ids[3:].monthly_adjustment_move_id)
        self.assertFalse(any(loan.line_ids.mapped('payment_date')))

    def test_first_zero_display_still_posts_principal_and_reduces_settlement_tail(self):
        loan = self._computed()
        loan.action_confirm()
        first = loan.flat_line_ids[0]
        self.assertEqual((first.flat_display_principal, first.interest, first.payment), (0, 0, 25353000))
        self.env['leasing.payment.wizard'].with_context(active_ids=first.ids).create({
            'journal_id': self.bank_journal.id, 'payment_date': date(2026, 10, 27),
        }).action_confirm_payment()
        payment = first.vendor_bill_id
        self.assertEqual(payment.state, 'posted')
        self.assertEqual(sum(payment.line_ids.filtered(
            lambda item: item.account_id == self.principal_account).mapped('debit')), 25353000)
        self.assertFalse(payment.line_ids.filtered(lambda item: item.account_id == self.accrued_account))
        self.assertEqual(loan.outstanding_balance, 762147000)
        bill = self._bill(loan)
        self.assertEqual(len(bill.invoice_line_ids), 35)
        self.assertEqual(bill.amount_total, 762147000)
        self.assertNotIn(first, bill.invoice_line_ids.early_settlement_schedule_line_id)

    def test_payment_before_confirm_is_not_allowed_for_flat(self):
        loan = self._computed()
        wizard = self.env['leasing.payment.wizard'].with_context(active_ids=loan.line_ids[:1].ids).create({
            'journal_id': self.bank_journal.id,
        })
        with self.assertRaisesRegex(UserError, 'Running'):
            wizard.action_confirm_payment()

    def test_currency_precision_and_non_idr_do_not_force_whole_rupiah(self):
        self.company.currency_id = self.env.ref('base.USD')
        loan = self._computed(harga_otr=1000, down_payment_leasing=0, total_hutang=1000,
                              amount_borrowed=1000, monthly_installment=40)
        self.assertTrue(any(line.interest != int(line.interest) for line in loan.line_ids))
        self.assertAlmostEqual(sum(loan.line_ids.mapped('principal')), 1000, places=2)
        self.assertEqual(loan.line_ids[-1].interest_balance, 0)

    def test_effective_values_match_original_function_for_all_supported_cases(self):
        cases = [
            {'monthly_installment': 7625812.39, 'interest_rate_annual': 9.007116413},
            {'monthly_installment': 0, 'interest_rate_annual': 9.007116413},
            {'monthly_installment': 0, 'interest_rate_annual': 0, 'payment_timing': 'anniversary'},
        ]
        for values in cases:
            with self.subTest(values=values):
                baseline = self._loan(state='draft')
                actual = self._loan(state='draft')
                for loan in baseline | actual:
                    loan.write({'harga_otr': 383000000, 'down_payment_leasing': 76600000,
                                'total_hutang': 306400000, 'amount_borrowed': 306400000, **values})
                OriginalLoan.action_compute_amortization_schedule(baseline)
                actual.action_compute_amortization_schedule()
                # Compare persisted monetary precision, not transient binary
                # float artifacts such as 5383234.149999999 before flush.
                self.env.flush_all()
                self.env.invalidate_all()
                self.assertEqual(self._financial_rows(actual), self._financial_rows(baseline))
                for name in ['monthly_installment', 'total_installment_payment', 'total_bunga',
                             'saldo_pokok_hutang', 'amount_borrowed', 'duration']:
                    self.assertEqual(actual[name], baseline[name], name)

    def test_legacy_effective_rows_and_payment_links_are_not_changed_on_read(self):
        loan = self._loan()
        self._entry(loan.line_ids[12])
        before = self._snapshot(loan)
        self.assertFalse(loan.schedule_compute_method)
        self.env.invalidate_all()
        self.assertFalse(loan.flat_schedule_needs_compute)
        self.assertEqual(self._snapshot(loan), before)

    def test_native_form_has_mutually_exclusive_tabs_and_readonly_flat_table(self):
        arch = etree.fromstring(self.env['account.loan'].get_view(
            view_id=self.env.ref('account_loans.account_loan_form_view').id, view_type='form')['arch'])
        old = arch.xpath("//page[@name='amortization_schedule']")[0]
        new = arch.xpath("//page[@name='flat_amortization_schedule']")[0]
        self.assertEqual(old.get('invisible'), "compute_method == 'flat'")
        self.assertEqual(new.get('invisible'), "compute_method != 'flat'")
        self.assertEqual(list(old.getparent()).index(new), list(old.getparent()).index(old) + 1)
        table = new.xpath('.//field[@name="flat_line_ids"]/list')[0]
        self.assertEqual(table.get('create'), '0')
        self.assertEqual(table.get('edit'), '0')
        self.assertEqual(table.get('delete'), '0')
        for name in ['date', 'payment_date', 'flat_display_principal', 'interest', 'payment', 'outstanding_balance', 'interest_balance']:
            self.assertTrue(table.xpath('./field[@name="%s"]' % name))
        self.assertEqual(self.env['account.loan']._fields['flat_line_ids'].comodel_name, 'account.loan.line')

    def test_flat_wizard_preview_does_not_write_and_apply_matches_schedule(self):
        loan = self._flat_loan()
        before = self._snapshot(loan)
        wizard = self.env['account.loan.compute.wizard'].with_context(active_id=loan.id, active_model='account.loan').create({
            'loan_id': loan.id,
        })
        self.assertEqual(wizard.compute_method, 'flat')
        self.assertEqual(wizard.flat_duration_months, 36)
        self.assertIn('Pokok dan Bunga Konstan', wizard.preview)
        self.assertNotIn('Efektif Ekuivalen', wizard.preview)
        self.assertIn('21,775,629', wizard.preview)
        self.assertEqual(wizard._flat_wizard_result()['rows'][0]['display_principal'], 0)
        wizard._onchange_compute_method()
        self.assertEqual(self._snapshot(loan), before)
        wizard.action_apply()
        self.assertFalse(loan.flat_schedule_needs_compute)
        self.assertEqual(loan.flat_line_ids[1].principal, 21775629)

    def test_flat_wizard_uses_months_not_rounded_whole_years(self):
        loan = self._flat_loan(duration=18, monthly_installment=0)
        wizard = self.env['account.loan.compute.wizard'].with_context(active_id=loan.id).create({'loan_id': loan.id})
        self.assertEqual(wizard.flat_duration_months, 18)
        wizard.action_save()
        self.assertEqual(len(loan.line_ids), 18)

    def test_flat_wizard_zero_rate_is_not_replaced_by_legacy_default(self):
        loan = self._flat_loan(interest_rate_annual=0, monthly_installment=0)
        wizard = self.env['account.loan.compute.wizard'].with_context(active_id=loan.id).create({'loan_id': loan.id})
        self.assertEqual(wizard.interest_rate, 0)
        self.assertEqual(wizard._flat_wizard_result()['total_interest'], 0)
        wizard.action_save()
        self.assertEqual(loan.total_bunga, 0)

    def test_flat_wizard_preview_and_compute_both_use_po_contract_fallback(self):
        loan = self._flat_loan(monthly_installment=0)
        # installment_amount is the existing stored PO-contract copy. Its
        # provider/copy dependencies are unchanged by the Flat calculator.
        loan.installment_amount = 25353000
        self.assertEqual(loan.installment_amount, 25353000)
        wizard = self.env['account.loan.compute.wizard'].with_context(active_id=loan.id).create({'loan_id': loan.id})
        wizard.flat_monthly_installment = 0
        self.assertEqual(wizard._flat_wizard_result()['rows'][1]['principal'], 21775629)
        wizard.action_save()
        self.assertEqual(loan.monthly_installment, 25353000)
        self.assertEqual(loan.flat_line_ids[1].principal, 21775629)

    def test_unchanged_running_auto_installment_write_preserves_signature(self):
        loan = self._computed(monthly_installment=0)
        loan.action_confirm()
        loan.monthly_installment = loan.monthly_installment
        self.assertEqual(loan.flat_installment_source, 'automatic')
        self.assertFalse(loan.flat_schedule_needs_compute)

    def test_effective_wizard_preview_keeps_original_output(self):
        loan = self._loan(state='draft')
        loan.monthly_installment = 7625812.39
        loan.interest_rate_annual = 9.007116413
        wizard = self.env['account.loan.compute.wizard'].with_context(active_id=loan.id).create({'loan_id': loan.id})
        OriginalWizard._compute_preview(wizard)
        expected = wizard.preview
        wizard.invalidate_recordset(['preview'])
        self.assertEqual(wizard.preview, expected)

    def test_flat_compute_obeys_native_access_rights(self):
        loan = self._flat_loan()
        fleet_user = new_test_user(self.env, login='flat_fleet_only', groups='fleet.fleet_group_user')
        with self.assertRaises(AccessError):
            loan.with_user(fleet_user).action_compute_amortization_schedule()

    def test_mixed_batch_invalid_flat_does_not_replace_effective_schedule(self):
        effective = self._loan(state='draft')
        flat = self._flat_loan(monthly_installment=1)
        before = self._financial_rows(effective)
        with self.assertRaises(UserError):
            (effective | flat).action_compute_amortization_schedule()
        self.assertEqual(self._financial_rows(effective), before)

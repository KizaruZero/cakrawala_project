from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time
from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged
from odoo.tests.common import new_test_user

from ..lib.effective2_schedule import Effective2ScheduleError, build_effective2_schedule
from .test_early_settlement import LeasingScheduleCommon


@tagged('post_install', '-at_install')
class TestLeasingEffective2(LeasingScheduleCommon):
    def _loan2(self, **values):
        count = values.pop('duration', 36)
        loan = self._loan(count=max(count, 1), state='draft', compute_method='effective_2')
        loan.write({
            'total_hutang': 100000000, 'amount_borrowed': 100000000,
            # Deliberately different: this method must use Total Hutang,
            # not silently replace it with Harga OTR minus DP.
            'harga_otr': 200000000, 'down_payment_leasing': 50000000,
            'monthly_installment': 3000000, 'interest_rate_annual': 12,
            'duration': count, 'due_date': date(2027, 1, 31), **values,
        })
        return loan

    def _computed2(self, **values):
        loan = self._loan2(**values)
        loan.action_compute_amortization_schedule()
        return loan

    def _amounts(self, loan):
        return loan.line_ids.read(['principal', 'interest', 'payment', 'outstanding_balance', 'interest_balance'])

    def test_first_and_second_rows_follow_requested_formula_from_total_hutang(self):
        loan = self._computed2()
        first, second = loan.line_ids[:2]
        self.assertEqual((first.interest, first.principal, first.payment, first.outstanding_balance),
                         (1000000, 2000000, 3000000, 98000000))
        self.assertEqual((second.interest, second.principal, second.payment, second.outstanding_balance),
                         (980000, 2020000, 3000000, 95980000))
        self.assertEqual(loan.amount_borrowed, 100000000)
        self.assertEqual(loan.total_hutang, 100000000)
        self.assertNotEqual(loan.amount_borrowed, loan.harga_otr - loan.down_payment_leasing)

    def test_all_rows_decline_from_previous_principal_and_final_row_clears_balance(self):
        loan = self._computed2()
        balance = Decimal('100000000')
        for index, line in enumerate(loan.line_ids):
            expected_interest = (balance * Decimal('0.01')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            expected_principal = balance if index == 35 else Decimal('3000000') - expected_interest
            balance -= expected_principal
            self.assertEqual(Decimal(str(line.interest)), expected_interest)
            self.assertEqual(Decimal(str(line.principal)), expected_principal)
            self.assertEqual(line.date, date(2027, 1, 31) + relativedelta(months=index))
        self.assertEqual(balance, 0)
        self.assertAlmostEqual(loan.line_ids[-1].outstanding_balance, 0, places=2)
        self.assertEqual(loan.line_ids[-1].interest_balance, 0)
        self.assertEqual(loan.line_ids[-1].payment, 16846243.29)

    def test_header_totals_include_first_interest_and_first_interest_balance_matches(self):
        loan = self._computed2()
        self.assertAlmostEqual(loan.total_bunga, 21846243.29, places=2)
        self.assertAlmostEqual(loan.total_installment_payment, 121846243.29, places=2)
        self.assertEqual(loan.saldo_pokok_hutang, 100000000)
        self.assertAlmostEqual(loan.line_ids[0].interest_balance, loan.total_bunga - loan.line_ids[0].interest, places=2)
        self.assertAlmostEqual(loan.line_ids[1].interest_balance, 19866243.29, places=2)
        self.assertEqual(loan.amount_borrowed_difference, 0)
        self.assertEqual(loan.interest_difference, 0)
        self.assertEqual(loan.duration_difference, 0)
        self.env.invalidate_all()
        loan._validate_effective2_schedule()

    def test_old_effective_and_flat_first_interest_remain_zero(self):
        for method in ['effective', 'flat']:
            loan = self._loan2(compute_method=method, harga_otr=110000000,
                               down_payment_leasing=10000000, advarr='in_advance_addm')
            loan.action_compute_amortization_schedule()
            self.assertEqual(loan.line_ids[0].interest, 0)
            self.assertEqual(loan.line_ids[0].principal, 3000000)
        self.assertEqual(self._computed2().line_ids[0].interest, 1000000)

    def test_cicilan_contract_is_required_and_error_does_not_replace_rows(self):
        loan = self._loan2(monthly_installment=0)
        before = loan.line_ids.read(['date', 'principal', 'interest'])
        with self.assertRaisesRegex(UserError, 'Cicilan'):
            loan.action_compute_amortization_schedule()
        self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest']), before)

    def test_existing_po_installment_is_contractual_fallback(self):
        loan = self._loan2(monthly_installment=0)
        loan.installment_amount = 3000000
        loan.action_compute_amortization_schedule()
        self.assertEqual(loan.monthly_installment, 3000000)
        self.assertEqual(loan.line_ids[0].interest, 1000000)

    def test_invalid_parameters_leave_source_rows_untouched(self):
        cases = [{'total_hutang': 0}, {'interest_rate_annual': -1}, {'duration': 0},
                 {'monthly_installment': -1}, {'monthly_installment': 500000},
                 {'monthly_installment': 103000000}, {'due_date': False}]
        for values in cases:
            with self.subTest(values=values):
                loan = self._loan2(**values)
                before = loan.line_ids.read(['date', 'principal', 'interest'])
                with self.assertRaises(UserError):
                    loan.action_compute_amortization_schedule()
                self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest']), before)

    def test_single_installment_includes_first_interest_and_requires_full_contract_amount(self):
        loan = self._computed2(duration=1, monthly_installment=101000000)
        self.assertEqual((loan.line_ids.principal, loan.line_ids.interest, loan.line_ids.payment),
                         (100000000, 1000000, 101000000))
        self.assertEqual(loan.line_ids.outstanding_balance, 0)
        loan = self._loan2(duration=1)
        with self.assertRaisesRegex(UserError, 'satu angsuran'):
            loan.action_compute_amortization_schedule()

    def test_zero_interest_rate_has_no_interest_and_exact_final_balance(self):
        loan = self._computed2(duration=4, interest_rate_annual=0, monthly_installment=25000000)
        self.assertEqual(loan.line_ids.mapped('interest'), [0, 0, 0, 0])
        self.assertEqual(loan.total_bunga, 0)
        self.assertEqual(loan.total_installment_payment, 100000000)
        self.assertEqual(loan.line_ids[-1].outstanding_balance, 0)

    def test_currency_rounding_uses_half_up_without_whole_rupiah_flat_policy(self):
        loan = self._computed2(total_hutang=100.5, amount_borrowed=100.5, duration=12, monthly_installment=9)
        self.assertEqual(loan.line_ids[0].interest, 1.01)
        self.assertEqual(loan.line_ids[0].principal, 7.99)
        self.assertAlmostEqual(loan.line_ids[-1].outstanding_balance, 0, places=2)

    def test_non_finite_inputs_are_rejected(self):
        for key in ['principal', 'annual_rate', 'installment']:
            values = {'principal': 1000, 'annual_rate': 12, 'months': 12,
                      'first_due_date': date(2027, 1, 31), 'installment': 90, key: float('nan')}
            with self.subTest(key=key), self.assertRaises(Effective2ScheduleError):
                build_effective2_schedule(**values)

    def test_changed_inputs_require_recompute_before_confirm(self):
        for values in [{'interest_rate_annual': 15}, {'monthly_installment': 3100000},
                       {'total_hutang': 110000000}, {'due_date': date(2027, 2, 1)}]:
            loan = self._computed2()
            loan.write(values)
            with self.assertRaisesRegex(UserError, 'Compute'):
                loan.action_confirm()
            loan.action_compute_amortization_schedule()
            loan.action_confirm()
            self.assertEqual(loan.state, 'running')

    def test_changed_amount_and_forged_signature_do_not_waive_formula_checks(self):
        loan = self._computed2()
        loan.line_ids[0].principal += 100
        with self.assertRaisesRegex(UserError, 'Compute'):
            loan.action_confirm()
        loan.effective2_schedule_signature = loan._effective2_fingerprint()
        with self.assertRaisesRegex(UserError, 'tidak sesuai'):
            loan.action_confirm()

    def test_draft_date_edit_preserves_amounts_and_can_confirm(self):
        loan = self._computed2()
        before = self._amounts(loan)
        with Form(loan, view='account_loans.account_loan_form_view') as form:
            with form.line_ids.edit(1) as row:
                row.date = loan.line_ids[1].date + relativedelta(days=1)
        self.assertEqual(self._amounts(loan), before)
        loan._validate_effective2_schedule()
        loan.action_confirm()

    def test_date_edit_cannot_bless_altered_principal(self):
        loan = self._computed2()
        loan.line_ids[1].principal += 100
        with self.assertRaisesRegex(UserError, 'Compute'):
            loan.line_ids[1].date += relativedelta(days=1)

    def test_running_parameters_rows_reset_and_compute_are_protected(self):
        loan = self._computed2()
        loan.action_confirm()
        before = self._amounts(loan)
        actions = [lambda: loan.write({'interest_rate_annual': 15}),
                   lambda: loan.write({'compute_method': 'effective'}),
                   lambda: loan.line_ids[0].write({'principal': 1}),
                   lambda: loan.line_ids[0].unlink(), lambda: loan.action_reset(),
                   lambda: loan.action_compute_amortization_schedule(),
                   lambda: self.env['account.loan.line'].create({'loan_id': loan.id, 'date': date(2035, 1, 1)})]
        for action in actions:
            with self.assertRaises(UserError):
                action()
        self.assertEqual(self._amounts(loan), before)

    def test_financial_history_blocks_draft_recompute_and_method_switch(self):
        loan = self._computed2()
        self._entry(loan.line_ids[0], state='draft')
        for action in [lambda: loan.action_compute_amortization_schedule(),
                       lambda: loan.write({'compute_method': 'flat'}), lambda: loan.action_reset()]:
            with self.assertRaises(UserError):
                action()

    def test_switching_to_old_effective_requires_recompute(self):
        loan = self._computed2()
        loan.compute_method = 'effective'
        with self.assertRaisesRegex(UserError, 'Compute'):
            loan.action_confirm()
        loan.action_compute_amortization_schedule()
        self.assertEqual(loan.line_ids[0].interest, 0)
        loan.action_confirm()

    def test_payment_posts_first_principal_and_interest_and_early_settlement_excludes_interest(self):
        loan = self._computed2()
        loan.action_confirm()
        first = loan.line_ids[0]
        self.env['leasing.payment.wizard'].with_context(active_ids=first.ids).create({
            'journal_id': self.bank_journal.id, 'payment_date': date(2026, 10, 28),
        }).action_confirm_payment()
        move = first.vendor_bill_id
        self.assertEqual(move.state, 'posted')
        self.assertEqual(sum(move.line_ids.filtered(lambda item: item.account_id == self.principal_account).mapped('debit')), 2000000)
        self.assertEqual(sum(move.line_ids.filtered(lambda item: item.account_id == self.accrued_account).mapped('debit')), 1000000)
        self.assertEqual(first.payment_date, move.date)
        self.assertEqual(loan.outstanding_balance, 98000000)
        bill = self._bill(loan)
        self.assertEqual(len(bill.invoice_line_ids), 35)
        self.assertAlmostEqual(bill.amount_total, 98000000, places=2)
        self.assertEqual(bill.invoice_line_ids[0].price_unit, 2020000)
        self.assertFalse(bill.invoice_line_ids.tax_ids)
        bill.action_post()
        self.assertEqual(loan.state, 'running')

    @freeze_time('2027-02-15')
    def test_accrual_starts_with_first_interest_but_is_not_a_payment(self):
        loan = self._computed2()
        loan.action_confirm()
        self.env['account.loan.line']._cron_generate_interest_adjustment()
        self.assertEqual(loan.line_ids[0].monthly_adjustment_move_id.amount_total, 1000000)
        self.assertFalse(loan.line_ids[1:].monthly_adjustment_move_id)
        self.assertFalse(any(loan.line_ids.mapped('payment_date')))

    def test_payment_before_confirm_is_not_allowed(self):
        loan = self._computed2()
        wizard = self.env['leasing.payment.wizard'].with_context(active_ids=loan.line_ids[:1].ids).create({
            'journal_id': self.bank_journal.id,
        })
        with self.assertRaisesRegex(UserError, 'Running'):
            wizard.action_confirm_payment()

    def test_preview_and_apply_share_formula_and_discard_does_not_write_parent(self):
        loan = self._loan2()
        before = loan.line_ids.read(['date', 'principal', 'interest'])
        wizard = self.env['account.loan.compute.wizard'].with_context(active_id=loan.id).create({'loan_id': loan.id})
        self.assertEqual(wizard.effective2_duration_months, 36)
        self.assertEqual(wizard.loan_amount, 100000000)
        self.assertIn('Bunga Efektif (Tanpa DP)', wizard.preview)
        self.assertIn('1,000,000', wizard.preview)
        wizard._onchange_compute_method()
        self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest']), before)
        wizard.action_apply()
        self.assertEqual(loan.line_ids[0].interest, 1000000)
        loan._validate_effective2_schedule()

    def test_wizard_switch_from_old_effective_does_not_mutate_parent_onchange(self):
        loan = self._loan2(compute_method='effective', duration=18)
        wizard = self.env['account.loan.compute.wizard'].with_context(active_id=loan.id).create({'loan_id': loan.id})
        wizard.compute_method = 'effective_2'
        wizard._onchange_compute_method()
        self.assertEqual(loan.compute_method, 'effective')
        self.assertEqual(wizard.effective2_duration_months, 18)
        wizard.action_save()
        self.assertEqual(loan.compute_method, 'effective_2')
        self.assertEqual(len(loan.line_ids), 18)

    def test_native_wizard_form_switch_initializes_months_and_preserves_parent_until_apply(self):
        loan = self._loan2(compute_method='effective', duration=18)
        before = loan.line_ids.read(['date', 'principal', 'interest'])
        wizard_model = self.env['account.loan.compute.wizard'].with_context(
            active_id=loan.id, default_loan_id=loan.id)
        with Form(wizard_model) as form:
            form.compute_method = 'effective_2'
            self.assertEqual(form.effective2_duration_months, 18)
            self.assertEqual(form.loan_amount, 100000000)
            self.assertIn('Bunga Efektif (Tanpa DP)', form.preview)
            self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest']), before)
            self.assertEqual(loan.compute_method, 'effective')
        form.record.action_apply()
        self.assertEqual(loan.compute_method, 'effective_2')
        self.assertEqual(len(loan.line_ids), 18)
        loan._validate_effective2_schedule()

    def test_wizard_missing_installment_is_actionable_and_does_not_replace_rows(self):
        loan = self._loan2(monthly_installment=0)
        before = loan.line_ids.ids
        wizard = self.env['account.loan.compute.wizard'].with_context(active_id=loan.id).create({'loan_id': loan.id})
        self.assertIn('Cicilan', wizard.preview)
        with self.assertRaisesRegex(UserError, 'Cicilan'):
            wizard.action_save()
        self.assertEqual(loan.line_ids.ids, before)

    def test_option_and_compute_button_exist_and_native_effective_table_is_reused(self):
        options = dict(self.env['account.loan']._fields['compute_method'].selection)
        self.assertEqual(options['effective_2'], 'Bunga Efektif (Tanpa DP)')
        wizard_options = dict(self.env['account.loan.compute.wizard']._fields['compute_method'].selection)
        self.assertEqual(wizard_options['effective_2'], 'Bunga Efektif (Tanpa DP)')
        arch = etree.fromstring(self.env['account.loan'].get_view(
            view_id=self.env.ref('account_loans.account_loan_form_view').id, view_type='form')['arch'])
        button = arch.xpath("//header/button[@string='Compute Efektif (Tanpa DP)']")[0]
        self.assertEqual(button.get('invisible'), "(state != 'draft' or compute_method != 'effective_2') or (schedule_source == 'import')")
        self.assertEqual(arch.xpath("//page[@name='amortization_schedule']")[0].get('invisible'), "compute_method == 'flat'")

    def test_compute_obeys_native_access_rights(self):
        loan = self._loan2()
        fleet = new_test_user(self.env, login='effective2_fleet_only', groups='fleet.fleet_group_user')
        with self.assertRaises(AccessError):
            loan.with_user(fleet).action_compute_amortization_schedule()

    def test_invalid_new_method_in_mixed_batch_does_not_replace_legacy_schedule(self):
        legacy = self._loan(state='draft')
        new = self._loan2(monthly_installment=0)
        before = legacy.line_ids.read(['date', 'principal', 'interest'])
        with self.assertRaises(UserError):
            (legacy | new).action_compute_amortization_schedule()
        self.assertEqual(legacy.line_ids.read(['date', 'principal', 'interest']), before)

from datetime import date
import importlib.util
from pathlib import Path
from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged
from odoo.tests.common import new_test_user

from ..lib.interest_conversion import InterestConversionError, build_converted_schedule
from .test_early_settlement import LeasingScheduleCommon


# Monetary principal column from BCA LEASEBACK!D24:D71 in the user-provided
# Tabel Angsuran V2 291026.xlsx. Independent golden values, not calculator output.
EXCEL_PRINCIPALS = [
    22875000, 15143698, 15277180, 15411839, 15547684, 15684727, 15822978, 15962448,
    16103147, 16245086, 16388276, 16532728, 16678454, 16825464, 16973770, 17123383,
    17274315, 17426577, 17580181, 17735139, 17891463, 18049165, 18208257, 18368751,
    18530660, 18693996, 18858772, 19025000, 19192693, 19361865, 19532528, 19704694,
    19878379, 20053594, 20230354, 20408672, 20588561, 20770036, 20953111, 21137799,
    21324116, 21512074, 21701690, 21892976, 22085949, 22280623, 22477012, 22675136,
]


@tagged('post_install', '-at_install')
class TestLeasingInterestConversion(LeasingScheduleCommon):
    def _converted(self, compute=True, **values):
        loan = self._loan(count=48, state='draft', use_rate_conversion=True,
                          interest_input_type='flat', quoted_interest_rate=5.5,
                          advarr='in_advance_addm')
        loan.write({
            'total_hutang': 900000000, 'amount_borrowed': 900000000,
            'harga_otr': 1000000000, 'down_payment_leasing': 100000000,
            'duration': 48, 'monthly_installment': 0, 'installment_amount': 0,
            'due_date': date(2024, 10, 3), **values,
        })
        if compute:
            loan.action_compute_amortization_schedule()
        return loan

    def _wizard(self, loan):
        action = loan.action_open_rate_conversion_wizard()
        return self.env['account.loan.compute.wizard'].with_context(**action['context']).create({})

    def test_flat_to_effective_all_48_excel_rows_and_rounding_reconcile(self):
        loan = self._converted()
        self.assertAlmostEqual(loan.converted_effective_rate, 10.57724079672, places=9)
        self.assertEqual(loan.converted_flat_rate, 5.5)
        self.assertEqual(loan.line_ids.mapped('principal'), EXCEL_PRINCIPALS)
        self.assertEqual(loan.line_ids.mapped('interest'), [22875000 - p for p in EXCEL_PRINCIPALS])
        self.assertEqual(loan.line_ids.mapped('payment'), [22875000] * 48)
        principal_balance, interest_balance = 900000000, 198000000
        for line in loan.line_ids:
            principal_balance -= line.principal
            interest_balance -= line.interest
            self.assertEqual(line.outstanding_balance, principal_balance)
            self.assertEqual(line.interest_balance, interest_balance)
        self.assertEqual((principal_balance, interest_balance), (0, 0))
        self.assertEqual(loan.line_ids[-1].interest, 199864)  # Rp3 correction vs rounded raw last interest.

    def test_effective_to_flat_round_trip_has_identical_contract_and_schedule(self):
        flat = self._converted()
        effective = self._converted(interest_input_type='effective', quoted_interest_rate=10.57724079672)
        self.assertEqual(effective.converted_flat_rate, 5.5)
        self.assertEqual(effective.monthly_installment, flat.monthly_installment)
        self.assertEqual(effective.line_ids.mapped('principal'), flat.line_ids.mapped('principal'))
        self.assertEqual(effective.line_ids.mapped('interest'), flat.line_ids.mapped('interest'))

    def test_header_totals_include_first_principal_without_double_dp(self):
        loan = self._converted()
        self.assertEqual(loan.amount_borrowed, 900000000)
        self.assertEqual(loan.total_bunga, 198000000)
        self.assertEqual(loan.interest, 198000000)
        self.assertEqual(loan.total_installment_payment, 1098000000)
        self.assertEqual(loan.amount_borrowed_difference, 0)
        self.assertEqual(loan.interest_difference, 0)
        self.assertEqual(loan.duration_difference, 0)
        other = self._converted(total_hutang=800000000, amount_borrowed=800000000)
        self.assertEqual(other.amount_borrowed, 800000000)  # Explicit Total Hutang wins over OTR-DP.

    def test_total_interest_quote_fills_before_any_schedule_exists(self):
        loan = self._converted(compute=False)
        loan.line_ids.unlink()
        before = loan.read(['monthly_installment', 'interest', 'conversion_signature'])
        self.assertEqual(loan.conversion_installment_preview, 22875000)
        self.assertEqual(loan.total_bunga, 198000000)
        self.assertFalse(loan.line_ids)
        self.assertEqual(loan.read(['monthly_installment', 'interest', 'conversion_signature']), before)
        loan.quoted_interest_rate = 6
        self.assertEqual(loan.conversion_installment_preview, 23250000)
        self.assertEqual(loan.total_bunga, 216000000)
        self.assertFalse(loan.line_ids)
        self.env.invalidate_all()
        self.assertEqual(loan.total_bunga, 216000000)

    def test_native_form_updates_total_interest_live_without_changing_old_rows(self):
        loan = self._converted()
        before = loan.line_ids.read(['date', 'principal', 'interest'])
        old_budget, old_signature = loan.interest, loan.conversion_signature
        with Form(loan, view='account_loans.account_loan_form_view') as form:
            form.quoted_interest_rate = 6
            self.assertEqual(form.conversion_installment_preview, 23250000)
            self.assertEqual(form.total_bunga, 216000000)
        self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest']), before)
        self.assertEqual((loan.interest, loan.conversion_signature), (old_budget, old_signature))
        self.assertTrue(loan.conversion_needs_compute)
        with self.assertRaisesRegex(UserError, 'Compute'):
            loan.action_confirm()
        loan.action_compute_amortization_schedule()
        self.assertEqual(loan.total_bunga, 216000000)
        self.assertEqual(sum(loan.line_ids.mapped('interest')), 216000000)

    def test_live_interest_quote_follows_effective_input_and_contract_override(self):
        loan = self._converted(compute=False, interest_input_type='effective', quoted_interest_rate=10.57724079672)
        loan.line_ids.unlink()
        self.assertEqual(loan.total_bunga, 198000000)
        loan.monthly_installment = 23000000
        self.assertEqual(loan.conversion_installment_preview, 23000000)
        self.assertEqual(loan.total_bunga, 204000000)
        loan.advarr = 'in_arrears'
        self.assertEqual(loan.total_bunga, 204000000)
        self.assertIn('kontrak diutamakan', loan.conversion_message)

    def test_incomplete_quote_clears_draft_preview_without_changing_running_totals(self):
        loan = self._converted(compute=False, advarr=False)
        loan.line_ids.unlink()
        self.assertEqual(loan.conversion_installment_preview, 0)
        self.assertEqual(loan.total_bunga, 0)
        self.assertIn('Advarr', loan.conversion_message)
        running = self._converted()
        running.action_confirm()
        before = running.read(['total_bunga', 'interest', 'total_installment_payment'])
        self.env.invalidate_all()
        self.assertEqual(running.read(['total_bunga', 'interest', 'total_installment_payment']), before)

    def test_upgrade_refreshes_only_unlinked_conversion_draft_summaries(self):
        draft = self._converted(compute=False)
        draft.line_ids.unlink()
        before = draft.read(['monthly_installment', 'interest', 'conversion_signature'])
        running = self._converted()
        running.action_confirm()
        legacy = self._loan()
        linked = self._converted(compute=False)
        self._entry(linked.line_ids[0], state='draft')
        self.env.flush_all()
        # Simulate summaries persisted by the previous version, with unrelated
        # legacy/history values deliberately distinct to prove migration scope.
        for loan, value in [(draft, 0), (running, 198000000), (legacy, 777), (linked, 888)]:
            self.env.cr.execute('UPDATE account_loan SET total_bunga = %s WHERE id = %s', (value, loan.id))
        (draft | running | legacy | linked).invalidate_recordset(['total_bunga'])
        path = Path(__file__).resolve().parents[1] / 'migrations/19.0.1.0.13/post-migrate.py'
        spec = importlib.util.spec_from_file_location('leasing_summary_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        for _ in range(2):
            migration.migrate(self.env.cr, '19.0.1.0.12')
            self.env.flush_all()
            (draft | running | legacy | linked).invalidate_recordset(['total_bunga'])
            self.assertEqual(draft.total_bunga, 198000000)
            self.assertEqual((running.total_bunga, legacy.total_bunga, linked.total_bunga), (198000000, 777, 888))
            self.assertEqual(draft.read(['monthly_installment', 'interest', 'conversion_signature']), before)
            self.assertFalse(draft.line_ids)

    def test_automatic_payment_recomputes_after_rate_and_tenor_changes(self):
        loan = self._converted()
        self.assertEqual(loan.conversion_auto_installment, 22875000)
        loan.quoted_interest_rate = 6
        self.assertTrue(loan.conversion_needs_compute)
        self.assertEqual(loan.conversion_installment_preview, 23250000)
        loan.action_compute_amortization_schedule()
        self.assertEqual(loan.monthly_installment, 23250000)
        loan.duration = 36
        loan.action_compute_amortization_schedule()
        self.assertEqual(len(loan.line_ids), 36)
        self.assertEqual(loan.monthly_installment, 29500000)

    def test_manual_contract_has_priority_and_discloses_rate_mismatch(self):
        loan = self._converted(monthly_installment=23000000)
        self.assertEqual(loan.monthly_installment, 23000000)
        self.assertEqual(loan.conversion_auto_installment, 0)
        self.assertIn('kontrak diutamakan', loan.conversion_message)
        self.assertAlmostEqual(loan.converted_flat_rate, 5.6666666666667)
        old = loan.line_ids.mapped('interest')
        loan.quoted_interest_rate = 7
        loan.action_compute_amortization_schedule()
        self.assertEqual(loan.line_ids.mapped('interest'), old)
        # An explicit user re-entry equal to the auto result is also contractual.
        other = self._converted()
        other.monthly_installment = 22875000
        self.assertEqual(other.conversion_auto_installment, 0)

    def test_stored_po_contract_fallback_matches_wizard_and_apply(self):
        loan = self._converted(compute=False, installment_amount=23000000)
        wizard = self._wizard(loan)
        self.assertEqual(wizard.conversion_contract_installment, 23000000)
        self.assertEqual(wizard._conversion_wizard_result()['installment'], 23000000)
        wizard.action_save()
        self.assertEqual(loan.monthly_installment, 23000000)

    def test_arrears_has_first_interest_and_uses_end_of_period_rate(self):
        advance = self._converted()
        arrears = self._converted(advarr='in_arrears')
        self.assertEqual(arrears.monthly_installment, advance.monthly_installment)
        self.assertLess(arrears.converted_effective_rate, advance.converted_effective_rate)
        self.assertGreater(arrears.line_ids[0].interest, 0)
        reverse = self._converted(advarr='in_arrears', interest_input_type='effective',
                                   quoted_interest_rate=arrears.converted_effective_rate)
        self.assertEqual(reverse.line_ids.mapped('interest'), arrears.line_ids.mapped('interest'))

    def test_zero_rate_fractional_currency_and_single_addm(self):
        loan = self._converted(total_hutang=1000, amount_borrowed=1000, duration=3, quoted_interest_rate=0)
        self.assertEqual(loan.line_ids.mapped('interest'), [0, 0, 0])
        self.assertEqual(loan.line_ids.mapped('payment'), [333.33, 333.33, 333.34])
        one = self._converted(total_hutang=1000, duration=1, quoted_interest_rate=0)
        self.assertEqual((one.line_ids.principal, one.line_ids.interest), (1000, 0))
        invalid = self._converted(compute=False, duration=1)
        with self.assertRaisesRegex(UserError, 'satu angsuran'):
            invalid.action_compute_amortization_schedule()

    def test_currency_precision_and_non_idr_do_not_force_whole_rupiah(self):
        loan = self._converted(flat_interest_rounding='currency')
        self.assertEqual(loan.line_ids[1].interest, 7731301.94)
        self.assertEqual(loan.total_bunga, 198000000)
        self.assertEqual(loan.line_ids[-1].interest_balance, 0)
        self.company.currency_id = self.env.ref('base.USD')
        non_idr = self._converted()
        self.assertEqual(non_idr.line_ids[1].interest, 7731301.94)
        self.assertEqual(non_idr.line_ids[-1].outstanding_balance, 0)

    def test_invalid_inputs_cannot_replace_any_existing_rows(self):
        for values in [{'quoted_interest_rate': -1}, {'duration': 0}, {'duration': 1201},
                       {'monthly_installment': 1}, {'monthly_installment': 900000000},
                       {'advarr': False}, {'due_date': False}]:
            loan = self._converted(compute=False, **values)
            before = loan.line_ids.read(['date', 'principal', 'interest'])
            with self.subTest(values=values), self.assertRaises(UserError):
                loan.action_compute_amortization_schedule()
            self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest']), before)

    def test_nonfinite_inputs_rejected(self):
        for key in ['principal', 'annual_rate', 'installment']:
            with self.subTest(key=key), self.assertRaises(InterestConversionError):
                build_converted_schedule(**{
                    'principal': 1000, 'annual_rate': 5.5, 'months': 12, 'installment': 0,
                    'input_type': 'flat', 'advance': True, 'first_due_date': date(2026, 1, 1), key: float('nan'),
                })

    def test_wizard_preview_cancel_never_writes_parent_and_apply_matches(self):
        loan = self._converted(compute=False)
        before = self._snapshot(loan)
        wizard = self._wizard(loan)
        self.assertTrue(wizard.conversion_preview)
        self.assertIn('10.5772407967', wizard.preview)
        self.assertEqual(wizard._conversion_wizard_result()['rows'][1]['interest'], 7731302)
        wizard._onchange_compute_method()
        self.assertEqual(self._snapshot(loan), before)
        wizard.action_save()
        self.assertEqual(loan.line_ids.mapped('principal'), EXCEL_PRINCIPALS)

    def test_native_form_input_and_wizard_both_conversion_directions(self):
        loan = self._converted(compute=False)
        with Form(loan, view='account_loans.account_loan_form_view') as form:
            self.assertEqual(form.interest_input_type, 'flat')
            self.assertAlmostEqual(form.converted_effective_rate, 10.57724079672, places=9)
        action = loan.action_open_rate_conversion_wizard()
        with Form(self.env['account.loan.compute.wizard'].with_context(**action['context'])) as form:
            form.conversion_input_type = 'effective'
            form.conversion_input_rate = 10.57724079672
            self.assertEqual(form.conversion_flat_rate, 5.5)
            self.assertIn('Alokasi Efektif', form.preview)
        form.record.action_save()
        self.assertEqual(loan.interest_input_type, 'effective')
        self.assertEqual(loan.line_ids.mapped('principal'), EXCEL_PRINCIPALS)

    def test_stale_inputs_or_rows_block_confirm_and_cannot_forge_signature(self):
        loan = self._converted()
        loan.quoted_interest_rate = 6
        with self.assertRaisesRegex(UserError, 'Compute'):
            loan.action_confirm()
        loan.action_compute_amortization_schedule()
        loan.line_ids[0].principal += 1
        original_date = loan.line_ids[1].date
        with self.assertRaisesRegex(UserError, 'Compute'):
            loan.line_ids[1].date = date(2024, 11, 4)
        self.assertEqual(loan.line_ids[1].date, original_date)
        with self.assertRaisesRegex(UserError, 'Compute'):
            loan.action_confirm()
        for metadata in ['conversion_signature', 'conversion_version', 'conversion_auto_installment']:
            with self.subTest(metadata=metadata), self.assertRaises(UserError):
                loan.write({metadata: 1 if metadata.endswith('installment') else 'forged'})

    def test_draft_date_edit_preserves_all_amounts_and_refreshes_signature(self):
        loan = self._converted(due_date=date(2027, 1, 31))
        self.assertEqual(loan.line_ids[1].date, date(2027, 2, 28))
        self.assertEqual(loan.line_ids[2].date, date(2027, 3, 31))
        before = loan.line_ids.read(['principal', 'interest'])
        with Form(loan, view='account_loans.account_loan_form_view') as form:
            with form.line_ids.edit(1) as row:
                row.date = date(2027, 2, 27)
        self.assertEqual(loan.line_ids.read(['principal', 'interest']), before)
        self.assertFalse(loan.conversion_needs_compute)
        loan.action_confirm()

    def test_confirm_payment_accrual_and_settlement_use_same_canonical_rows(self):
        loan = self._converted()
        loan.action_confirm()
        first, second = loan.line_ids[:2]
        self.assertFalse(first._generate_monthly_adjustment_entry())
        second._generate_monthly_adjustment_entry()
        self.assertEqual(second.monthly_adjustment_move_id.amount_total, 7731302)
        self.assertEqual(
            second.monthly_adjustment_move_id.line_ids.mapped('analytic_distribution'),
            [{str(self.analytic.id): 100}, {str(self.analytic.id): 100}],
        )
        # ADDM 1st installment has journal_state = 'posted' without forming a journal
        self.assertEqual(first.journal_state, 'posted')
        self.assertFalse(first.vendor_bill_id)
        self.env['leasing.payment.wizard'].with_context(active_ids=first.ids).create({
            'journal_id': self.bank_journal.id, 'payment_date': date(2026, 10, 29),
        }).action_confirm_payment()
        self.assertFalse(first.vendor_bill_id)
        self.assertEqual(first.journal_state, 'posted')
        self.assertFalse(first.payment_date)
        self.assertEqual(loan.outstanding_balance, 877125000)
        bill = self._bill(loan)
        self.assertEqual(len(bill.invoice_line_ids), 47)
        self.assertEqual(bill.amount_total, 877125000)
        bill.action_post()

    def test_addm_vs_addb_first_installment_journal_and_voucher_behavior(self):
        # 1. ADDM: Line 1 is automatically Posted with no journal; paying lines 1 & 2 only creates journal for line 2
        addm_loan = self._converted(advarr='in_advance_addm')
        addm_loan.action_confirm()
        addm_first, addm_second, addm_third = addm_loan.line_ids[:3]
        self.assertEqual(addm_first.journal_state, 'posted')
        self.assertFalse(addm_first.vendor_bill_id)
        self.assertFalse(addm_second.journal_state)
        self.env['leasing.payment.wizard'].with_context(active_ids=(addm_first | addm_second).ids).create({
            'journal_id': self.bank_journal.id, 'payment_date': date(2026, 10, 29),
        }).action_confirm_payment()
        self.assertFalse(addm_first.vendor_bill_id)
        self.assertEqual(addm_first.journal_state, 'posted')
        self.assertTrue(addm_second.vendor_bill_id)
        self.assertEqual(addm_second.journal_state, 'posted')
        self.assertNotIn('Angsuran ke-1 - Principal', addm_second.vendor_bill_id.line_ids.mapped('name'))
        self.assertIn('Angsuran ke-2 - Principal', addm_second.vendor_bill_id.line_ids.mapped('name'))
        self.assertEqual(
            addm_second.vendor_bill_id.line_ids.mapped('analytic_distribution'),
            [{str(self.analytic.id): 100}] * len(addm_second.vendor_bill_id.line_ids),
        )

        # If Payment Voucher Leasing module is installed, verify voucher flow on ADDM vs ADDB
        if 'leasing.payment.voucher' in self.env:
            with self.assertRaisesRegex(UserError, 'ADDM'):
                addm_first.action_create_payment_voucher_leasing()
            v_action = (addm_first | addm_third).action_create_payment_voucher_leasing()
            voucher = self.env['leasing.payment.voucher'].browse(v_action['res_id'])
            self.assertEqual(voucher.line_ids.mapped('installment_number'), [3])
            voucher.write({'state': 'approved'})
            self.env['leasing.voucher.pay.wizard'].create({
                'voucher_id': voucher.id,
                'journal_id': self.bank_journal.id,
                'payment_date': date(2026, 10, 30),
            }).action_confirm_payment()
            self.assertFalse(addm_first.vendor_bill_id)
            self.assertEqual(addm_first.journal_state, 'posted')
            self.assertTrue(addm_third.vendor_bill_id)
            self.assertEqual(addm_third.journal_state, 'posted')
            self.assertNotIn('Angsuran ke-1 - Principal', addm_third.vendor_bill_id.line_ids.mapped('name'))
            self.assertIn('Angsuran ke-3 - Principal', addm_third.vendor_bill_id.line_ids.mapped('name'))

        # 2. ADDB (in_arrears): Line 1 starts unpaid and creates journal normally when paid
        addb_loan = self._converted(advarr='in_arrears')
        addb_loan.action_confirm()
        addb_first = addb_loan.line_ids[0]
        self.assertFalse(addb_first.journal_state)
        self.assertFalse(addb_first.vendor_bill_id)
        self.env['leasing.payment.wizard'].with_context(active_ids=addb_first.ids).create({
            'journal_id': self.bank_journal.id, 'payment_date': date(2026, 10, 29),
        }).action_confirm_payment()
        self.assertTrue(addb_first.vendor_bill_id)
        self.assertEqual(addb_first.journal_state, 'posted')
        self.assertIn('Angsuran ke-1 - Principal', addb_first.vendor_bill_id.line_ids.mapped('name'))

    def test_running_parameters_and_financial_rows_are_protected(self):
        loan = self._converted()
        loan.action_confirm()
        before = self._snapshot(loan)
        for action in [lambda: loan.write({'quoted_interest_rate': 6}),
                       lambda: loan.write({'monthly_installment': 24000000}),
                       lambda: loan.write({'interest_input_type': 'effective'}),
                       lambda: loan.line_ids[0].write({'principal': 1}),
                       loan.line_ids[0].unlink, loan.action_reset, loan.action_compute_amortization_schedule]:
            with self.assertRaises(UserError):
                action()
        self.assertEqual(self._snapshot(loan), before)

    def test_draft_history_blocks_recompute_and_payment_before_confirm(self):
        loan = self._converted()
        wizard = self.env['leasing.payment.wizard'].with_context(active_ids=loan.line_ids[:1].ids).create({
            'journal_id': self.bank_journal.id})
        with self.assertRaisesRegex(UserError, 'Running'):
            wizard.action_confirm_payment()
        self._entry(loan.line_ids[0], state='draft')
        before = self._snapshot(loan)
        with self.assertRaises(UserError):
            loan.action_compute_amortization_schedule()
        self.assertEqual(self._snapshot(loan), before)

    def test_legacy_draft_explicit_opt_in_preview_and_legacy_running_unchanged(self):
        legacy = self._loan(count=12, state='draft', compute_method='effective', advarr='in_advance_addm')
        legacy.write({'monthly_installment': 7000000, 'interest_rate_annual': 12,
                      'total_hutang': 60000000, 'amount_borrowed': 60000000})
        legacy.action_compute_amortization_schedule()
        self.assertFalse(legacy.use_rate_conversion)
        before = self._snapshot(legacy)
        wizard = self._wizard(legacy)
        self.assertTrue(wizard.conversion_preview)
        self.assertEqual(self._snapshot(legacy), before)
        wizard.action_save()
        self.assertTrue(legacy.use_rate_conversion)
        legacy._validate_converted_schedule()
        running = self._loan()
        before = self._snapshot(running)
        self.env.invalidate_all()
        self.assertFalse(running.use_rate_conversion)
        self.assertEqual(self._snapshot(running), before)

    def test_new_create_defaults_to_conversion_without_migrating_legacy_opt_out(self):
        loan = self.env['account.loan'].create({'date': date(2026, 10, 29)})
        self.assertTrue(loan.use_rate_conversion)
        self.assertEqual(loan.interest_input_type, 'flat')
        self.assertEqual(loan.compute_method, 'effective')
        self.assertFalse(self._loan().use_rate_conversion)

    def test_cannot_switch_conversion_to_legacy_or_create_running(self):
        loan = self._converted()
        for values in [{'compute_method': 'flat'}, {'use_rate_conversion': False}]:
            with self.assertRaises(UserError):
                loan.write(values)
        with self.assertRaisesRegex(UserError, 'Draft'):
            self.env['account.loan'].create({'state': 'running'})

    def test_compute_access_and_mixed_batch_atomicity(self):
        good = self._converted()
        bad = self._converted(compute=False, monthly_installment=1)
        before = self._snapshot(good)
        with self.assertRaises(UserError):
            (good | bad).action_compute_amortization_schedule()
        self.assertEqual(self._snapshot(good), before)
        fleet = new_test_user(self.env, login='conversion_fleet', groups='fleet.fleet_group_user')
        with self.assertRaises(AccessError):
            good.with_user(fleet).action_compute_amortization_schedule()

    def test_native_form_hides_compute_method_and_has_single_canonical_table(self):
        arch = etree.fromstring(self.env['account.loan'].get_view(view_type='form')['arch'])
        self.assertTrue(all(field.get('invisible') == '1' for field in arch.xpath('//field[@name="compute_method"]')))
        self.assertTrue(arch.xpath('//header/button[@name="action_open_rate_conversion_wizard"]'))
        self.assertTrue(arch.xpath('//page[@name="amortization_schedule"]/field[@name="line_ids"]'))
        self.assertEqual(arch.xpath('//field[@name="monthly_installment"]')[0].get('invisible'), 'use_rate_conversion')
        rate_fields = arch.xpath('//field[@name="interest_rate_annual"]')
        self.assertEqual(len(rate_fields), 2)
        self.assertIn('use_rate_conversion', rate_fields[0].get('invisible'))
        self.assertEqual(rate_fields[1].get('invisible'), '1')
        self.assertTrue(all(field.get('invisible') == '1' for field in arch.xpath('//field[@name="interest"][not(ancestor::list)]')))

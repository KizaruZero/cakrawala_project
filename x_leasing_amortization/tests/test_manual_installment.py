import hashlib
import json
from datetime import date

from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from ..models.account_loan_conversion import _PARAMETERS
from .test_early_settlement import LeasingScheduleCommon
from .test_interest_conversion import TestLeasingInterestConversion
from .test_schedule_import import TestLeasingScheduleImport


@tagged('post_install', '-at_install')
class TestLeasingManualInstallment(LeasingScheduleCommon):
    _converted = TestLeasingInterestConversion._converted
    _wizard = TestLeasingInterestConversion._wizard
    _data = TestLeasingScheduleImport._data
    _import_wizard = TestLeasingScheduleImport._wizard

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.currency.rounding = 1

    def _manual(self, compute=True, **values):
        return self._converted(compute=compute, **{
            'total_hutang': 544770000, 'duration': 48, 'quoted_interest_rate': 4.6404,
            'due_date': date(2026, 1, 21), 'leasing_installment': 13456000, **values})

    def _assert_manual_schedule(self, loan, installment):
        self.assertEqual(set(loan.line_ids.mapped('payment')), {installment})
        self.assertEqual(sum(loan.line_ids.mapped('principal')), loan.total_hutang)
        self.assertEqual(sum(loan.line_ids.mapped('interest')), installment * loan.duration - loan.total_hutang)
        self.assertEqual(loan.total_installment_payment, installment * loan.duration)
        self.assertEqual(loan.total_bunga, installment * loan.duration - loan.total_hutang)
        self.assertEqual(loan.line_ids[-1].outstanding_balance, 0)
        self.assertEqual(loan.line_ids[-1].interest_balance, 0)
        loan._validate_converted_schedule()

    def test_manual_13456000_keeps_formula_13456001_and_balances_contract(self):
        loan = self._manual()
        self.assertEqual(loan.conversion_installment_preview, 13456001)
        self.assertEqual(loan.leasing_installment, 13456000)
        self.assertEqual(loan.monthly_installment, 13456000)
        self.assertEqual(loan.total_bunga, 101118000)
        self.assertEqual(loan.line_ids[0].interest, 0)
        self.assertEqual(loan.line_ids[0].principal, 13456000)
        self._assert_manual_schedule(loan, 13456000)
        loan.action_confirm()
        self._assert_manual_schedule(loan, 13456000)

    def test_addb_uses_same_manual_total_with_interest_from_first_row(self):
        loan = self._manual(advarr='in_arrears')
        self.assertGreater(loan.line_ids[0].interest, 0)
        self._assert_manual_schedule(loan, 13456000)

    def test_form_input_quotes_interest_but_requires_explicit_compute(self):
        loan = self._manual(leasing_installment=0)
        rows = loan.line_ids.read(['date', 'principal', 'interest'])
        with Form(loan) as form:
            form.leasing_installment = 13456000
            self.assertEqual(form.conversion_installment_preview, 13456001)
            self.assertEqual(form.total_bunga, 101118000)
        self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest']), rows)
        self.assertTrue(loan.conversion_needs_compute)
        with self.assertRaises(UserError):
            loan.action_confirm()
        loan.action_compute_amortization_schedule()
        self._assert_manual_schedule(loan, 13456000)

    def test_clear_after_compute_restores_formula_not_old_manual_shadow(self):
        loan = self._manual()
        loan.leasing_installment = 0
        self.assertEqual(loan.conversion_installment_preview, 13456001)
        self.assertTrue(loan.conversion_needs_compute)
        loan.action_compute_amortization_schedule()
        self._assert_manual_schedule(loan, 13456001)

    def test_manual_overrides_old_monthly_and_po_contract_priority(self):
        loan = self._manual(monthly_installment=13457000, installment_amount=13458000)
        self._assert_manual_schedule(loan, 13456000)
        loan.leasing_installment = 0
        self.assertEqual(loan.conversion_installment_preview, 13458000)
        loan.action_compute_amortization_schedule()
        self._assert_manual_schedule(loan, 13458000)

    def test_wizard_preview_apply_and_clear_follow_header_manual(self):
        loan = self._manual(compute=False)
        wizard = self._wizard(loan)
        self.assertEqual(wizard.conversion_contract_installment, 13456000)
        self.assertEqual(float(wizard._conversion_wizard_result()['installment']), 13456000)
        wizard.conversion_contract_installment = 13455000
        wizard.action_save()
        self.assertEqual(loan.leasing_installment, 13455000)
        self._assert_manual_schedule(loan, 13455000)
        wizard = self._wizard(loan)
        wizard.conversion_contract_installment = 0
        wizard.action_save()
        self.assertFalse(loan.leasing_installment)
        self._assert_manual_schedule(loan, 13456001)

    def test_running_and_transaction_linked_draft_reject_manual_changes(self):
        loan = self._manual()
        loan.action_confirm()
        for amount in (0, 13455000):
            with self.assertRaises(UserError):
                loan.leasing_installment = amount
        self._assert_manual_schedule(loan, 13456000)
        draft = self._manual()
        self._entry(draft.line_ids[0], state='draft')
        with self.assertRaises(UserError):
            draft.leasing_installment = 13455000
        self._assert_manual_schedule(draft, 13456000)

    def test_invalid_inputs_and_too_small_payment_do_not_replace_rows(self):
        loan = self._manual()
        for amount in (-1, float('nan'), float('inf')):
            with self.assertRaises(UserError):
                loan.leasing_installment = amount
        rows = loan.line_ids.read(['date', 'principal', 'interest'])
        loan.leasing_installment = 1
        with self.assertRaises(UserError):
            loan.action_compute_amortization_schedule()
        self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest']), rows)

    def test_zero_input_retains_exact_preexisting_signature_payload(self):
        loan = self._manual(leasing_installment=0)
        self.assertNotIn('leasing_installment', _PARAMETERS)
        values = {name: loan[name].id if loan._fields[name].type == 'many2one' else loan[name]
                  for name in sorted(_PARAMETERS)}
        values.update({'auto': loan.conversion_auto_installment, 'version': loan.conversion_version,
            'currency': loan.currency_id.name, 'rounding': loan.currency_id.rounding,
            'rows': [(str(line.date), line.principal, line.interest, line.date_is_manual)
                     for line in loan.line_ids.sorted(lambda line: (line.date, line.id))]})
        old_signature = hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()
        self.assertEqual(loan.conversion_signature, old_signature)
        loan.action_confirm()
        self.assertEqual(loan._conversion_fingerprint(), old_signature)

    def test_view_field_directly_below_conversion_and_draft_only(self):
        root = etree.fromstring(self.env['account.loan'].get_view(view_type='form')['arch'])
        node = root.xpath("//field[@name='conversion_installment_preview']")[0]
        self.assertEqual(node.getnext().get('name'), 'leasing_installment')
        self.assertEqual(node.getnext().get('readonly'), "state != 'draft'")

    def test_effective_input_uses_manual_payment_consistently(self):
        loan = self._manual(interest_input_type='effective', quoted_interest_rate=9)
        self._assert_manual_schedule(loan, 13456000)

    def test_imported_schedules_cannot_use_manual_compute_input(self):
        action = self._import_wizard(*self._data()).action_import()
        loan = self.env['account.loan'].browse(action['domain'][0][2])
        before = self._snapshot(loan)
        with self.assertRaises(UserError), self.cr.savepoint():
            loan.leasing_installment = 500
        self.assertEqual(self._snapshot(loan), before)

    def test_manual_canonical_rows_drive_payment_accrual_and_settlement(self):
        loan = self._manual()
        loan.action_confirm()
        second = loan.line_ids[1]
        move = second._generate_monthly_adjustment_entry()
        self.assertEqual(move.amount_total, second.interest)
        self.env['leasing.payment.wizard'].with_context(active_ids=second.ids).create({
            'journal_id': self.bank_journal.id, 'payment_date': date(2026, 10, 29),
        }).action_confirm_payment()
        self.assertEqual(second.payment, 13456000)
        self.assertEqual(second.vendor_bill_id.state, 'posted')
        self.assertEqual(sum(second.vendor_bill_id.line_ids.mapped('balance')), 0)
        bill = self._bill(loan)
        self.assertEqual(bill.amount_total, sum(loan.line_ids[2:].mapped('principal')))

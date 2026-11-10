from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from .test_early_settlement import LeasingScheduleCommon
from .test_schedule_import import TestLeasingScheduleImport


@tagged('post_install', '-at_install')
class TestLeasingDownPayment(LeasingScheduleCommon):
    def _draft(self, **values):
        return self.env['account.loan'].create({
            'company_id': self.company.id, 'harga_otr': 608200000,
            'date': date(2026, 11, 1), 'due_date': date(2026, 12, 1),
            'advarr': 'in_arrears', 'duration': 48, 'quoted_interest_rate': 5.5,
            **values,
        })

    def test_fixed_and_percentage_compute_principal_on_create_and_api_write(self):
        loan = self._draft(down_payment_leasing=60820000)
        self.assertEqual((loan.total_hutang, loan.amount_borrowed), (547380000, 547380000))
        loan.write({'down_payment_type': 'percentage', 'down_payment_percentage': 20})
        self.assertEqual(loan.down_payment_leasing, 121640000)
        self.assertEqual(loan.total_hutang, 486560000)
        loan.harga_otr = 1000000000
        self.assertEqual((loan.down_payment_leasing, loan.total_hutang), (200000000, 800000000))
        loan.write({'down_payment_type': 'fixed', 'down_payment_leasing': 100000000})
        self.assertEqual((loan.total_hutang, loan.amount_borrowed), (900000000, 900000000))
        loan.write({'total_hutang': 1, 'amount_borrowed': 1})
        self.assertEqual((loan.total_hutang, loan.amount_borrowed), (900000000, 900000000))
        loan.flush_recordset()
        loan.invalidate_recordset()
        self.assertEqual(loan.total_hutang, 900000000)

    def test_form_live_percentage_preview_and_readonly_amount(self):
        loan = self._draft()
        with Form(loan, view='account_loans.account_loan_form_view') as form:
            form.down_payment_type = 'percentage'
            form.down_payment_percentage = 10
            self.assertEqual(form.down_payment_leasing, 60820000)
            self.assertEqual(form.total_hutang, 547380000)
            self.assertTrue(form._get_modifier('down_payment_leasing', 'readonly'))
            self.assertTrue(form._get_modifier('total_hutang', 'readonly'))
        self.assertEqual(loan.amount_borrowed, 547380000)

    def test_currency_rounding_zero_dp_and_invalid_input(self):
        loan = self._draft(harga_otr=100.05, down_payment_type='percentage', down_payment_percentage=12.3456)
        expected = loan.currency_id.round(100.05 * 12.3456 / 100)
        self.assertEqual(loan.down_payment_leasing, expected)
        self.assertEqual(loan.total_hutang, loan.currency_id.round(100.05 - expected))
        loan.down_payment_percentage = 0
        self.assertEqual(loan.total_hutang, 100.05)
        fixed = self._draft(harga_otr=100.005, down_payment_leasing=20.005)
        self.assertEqual(fixed.total_hutang, fixed.currency_id.round(
            fixed.harga_otr - fixed.down_payment_leasing))
        for values in ({'down_payment_percentage': -1}, {'down_payment_percentage': 101},
                       {'down_payment_type': 'fixed', 'down_payment_leasing': -1},
                       {'down_payment_type': 'fixed', 'down_payment_leasing': 101}):
            with self.subTest(values=values), self.assertRaises(ValidationError), self.env.cr.savepoint():
                loan.write(values)

    def test_legacy_running_keeps_principal_and_rejects_new_dp_changes(self):
        loan = self._loan()
        before = loan.read(['total_hutang', 'amount_borrowed', 'line_ids'])
        loan.vendor_id = self.vendor
        self.assertEqual(loan.read(['total_hutang', 'amount_borrowed', 'line_ids']), before)
        with self.assertRaises(UserError):
            loan.write({'down_payment_type': 'percentage', 'down_payment_percentage': 10})

    def test_dp_change_invalidates_schedule_without_rewriting_existing_lines(self):
        loan = self._draft(harga_otr=1000000000, down_payment_type='percentage', down_payment_percentage=10)
        loan.action_compute_amortization_schedule()
        self.assertAlmostEqual(sum(loan.line_ids.mapped('principal')), 900000000, places=2)
        before = loan.line_ids.read(['date', 'principal', 'interest'])
        loan.down_payment_percentage = 20
        self.assertEqual(loan.total_hutang, 800000000)
        self.assertTrue(loan.conversion_needs_compute)
        self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest']), before)
        loan.action_compute_amortization_schedule()
        self.assertAlmostEqual(sum(loan.line_ids.mapped('principal')), 800000000, places=2)
        self.assertFalse(loan.conversion_needs_compute)

    # Use the existing import fixture builders without inheriting their tests.
    _data = TestLeasingScheduleImport._data
    _wizard = TestLeasingScheduleImport._wizard

    def test_import_rejects_principal_mismatch_without_rewriting_file(self):
        headers, rows = self._data()
        headers[0]['Harga OTR'] = 1600
        with self.assertRaisesRegex(UserError, 'Harga OTR'):
            self._wizard(headers, rows).action_import()

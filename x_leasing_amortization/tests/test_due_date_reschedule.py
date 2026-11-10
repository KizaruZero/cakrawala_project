from datetime import date
from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_early_settlement import LeasingScheduleCommon
from .test_schedule_dates import TestLeasingScheduleDates
from .test_flat_schedule import TestLeasingFlatSchedule
from .test_interest_conversion import TestLeasingInterestConversion
from .test_schedule_import import TestLeasingScheduleImport


@tagged('post_install', '-at_install')
class TestLeasingDueDateReschedule(LeasingScheduleCommon):
    _effective = TestLeasingScheduleDates._effective
    _flat_loan = TestLeasingFlatSchedule._flat_loan
    _computed = TestLeasingFlatSchedule._computed
    _converted = TestLeasingInterestConversion._converted
    _data = TestLeasingScheduleImport._data
    _wizard = TestLeasingScheduleImport._wizard
    _import = TestLeasingScheduleImport._import

    def _money(self, loan):
        return loan.line_ids.read(['principal', 'interest', 'payment', 'outstanding_balance', 'interest_balance'])

    def test_second_march_first_then_april_first_without_changing_amounts(self):
        first = date(2026, 1, 21)
        for loan in (self._converted(duration=4, due_date=first),
                     self._effective(due_date=first), self._computed(duration=4, due_date=first, monthly_installment=0)):
            with self.subTest(loan=loan.id):
                before = self._money(loan)
                first_id = loan.line_ids[0].id
                loan.second_installment_due_date = date(2026, 3, 1)
                loan.action_apply_second_installment_due_date()
                self.assertEqual(loan.line_ids.mapped('date'), [first, date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)])
                self.assertEqual(loan.line_ids[0].id, first_id)
                self.assertEqual(loan.due_date, first)
                self.assertEqual(self._money(loan), before)

    def test_large_forward_then_backward_shift_keeps_original_installment_order(self):
        loan = self._converted(duration=6, due_date=date(2026, 1, 21))
        ids = loan.line_ids.ids
        money = self._money(loan)
        for anchor in (date(2026, 9, 1), date(2026, 2, 1)):
            loan.second_installment_due_date = anchor
            loan.action_apply_second_installment_due_date()
            self.assertEqual(loan.line_ids.ids, ids)
            self.assertEqual(loan.line_ids[1].date, anchor)
            self.assertEqual(self._money(loan), money)

    def test_month_end_clamping_uses_second_anchor_not_previous_clamped_date(self):
        for year, last_day in ((2027, 28), (2028, 29)):
            loan = self._converted(duration=4, due_date=date(year, 1, 1))
            loan.second_installment_due_date = date(year, 1, 31)
            loan.action_apply_second_installment_due_date()
            self.assertEqual(loan.line_ids.mapped('date'), [date(year, 1, 1), date(year, 1, 31),
                                                           date(year, 2, last_day), date(year, 3, 31)])

    def test_invalid_or_missing_target_rejected_atomically(self):
        loan = self._converted(duration=4, due_date=date(2026, 1, 21))
        before = loan.line_ids.read(['date', 'principal', 'interest'])
        for target in (False, date(2026, 1, 21), date(2026, 1, 20)):
            loan.second_installment_due_date = target
            with self.assertRaises(UserError):
                loan.action_apply_second_installment_due_date()
            self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest']), before)
        single = self._converted(duration=1, quoted_interest_rate=0)
        single.second_installment_due_date = date(2027, 1, 1)
        with self.assertRaisesRegex(UserError, 'dua angsuran'):
            single.action_apply_second_installment_due_date()

    def test_transaction_linked_drafts_are_protected(self):
        loan = self._converted(duration=4)
        loan.second_installment_due_date = date(2026, 3, 1)
        self._entry(loan.line_ids[0], state='draft')
        before = loan.line_ids.read(['date', 'principal', 'interest'])
        with self.assertRaises(UserError):
            loan.action_apply_second_installment_due_date()
        self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest']), before)

    def test_running_all_policies_allow_first_posted_but_preserve_transactions(self):
        for loan in (self._converted(duration=4), self._effective(),
                     self._computed(duration=4, monthly_installment=0), self._import()):
            loan.action_confirm()
            self.assertEqual(loan.state, 'running')
            first = loan.line_ids[0]
            entry = self._entry(first)
            before = self._money(loan)
            first_date, posted_date = first.date, entry.date
            loan.second_installment_due_date = date(2027, 3, 1)
            loan.action_apply_second_installment_due_date()
            self.assertEqual(first.date, first_date)
            self.assertEqual(entry.date, posted_date)
            self.assertEqual(entry.state, 'posted')
            self.assertEqual(loan.line_ids[1].date, date(2027, 3, 1))
            self.assertEqual(loan.line_ids[2].date, date(2027, 4, 1))
            self.assertEqual(self._money(loan), before)
            with self.assertRaises(UserError):
                loan.line_ids[1].date = date(2027, 3, 2)

    def test_running_linked_target_is_rejected_atomically(self):
        for state, native, accrued in [('draft', False, False), ('posted', False, False),
                                       ('posted', True, False), ('posted', False, True)]:
            loan = self._converted(duration=4)
            loan.action_confirm()
            self._entry(loan.line_ids[2], state=state, native=native, accrued=accrued)
            loan.second_installment_due_date = date(2027, 3, 1)
            before = loan.line_ids.read(['date', 'principal', 'interest'])
            with self.assertRaisesRegex(UserError, 'jurnal/pembayaran'):
                loan.action_apply_second_installment_due_date()
            self.assertEqual(loan.line_ids.read(['date', 'principal', 'interest']), before)

    def test_closed_states_stay_protected_and_button_is_in_header(self):
        for state in ('closed', 'cancelled'):
            loan = self._loan(state=state)
            with self.assertRaises(UserError):
                loan.second_installment_due_date = date(2027, 3, 1)
            with self.assertRaises(UserError):
                loan.action_apply_second_installment_due_date()
        arch = etree.fromstring(self.env['account.loan'].get_view(view_type='form')['arch'])
        buttons = arch.xpath("//button[@name='action_apply_second_installment_due_date']")
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].getparent().tag, 'header')
        self.assertIn("'running'", buttons[0].get('invisible'))
        self.assertIn("'running'", arch.xpath("//field[@name='second_installment_due_date']")[0].get('readonly'))

    def test_recompute_keeps_second_date_and_schedule_can_be_confirmed(self):
        loan = self._converted(duration=4, due_date=date(2026, 1, 21))
        loan.second_installment_due_date = date(2026, 3, 1)
        loan.action_apply_second_installment_due_date()
        loan.action_compute_amortization_schedule()
        self.assertEqual(loan.line_ids.mapped('date'), [date(2026, 1, 21), date(2026, 3, 1),
                                                       date(2026, 4, 1), date(2026, 5, 1)])
        self.assertFalse(loan.conversion_needs_compute)
        loan.action_confirm()
        self.assertEqual(loan.state, 'running')

    def test_imported_draft_date_shift_preserves_contract_principal_and_interest(self):
        loan = self._import()
        before = self._money(loan)
        first = loan.line_ids[0].date
        loan.second_installment_due_date = date(2027, 1, 1)
        loan.action_apply_second_installment_due_date()
        self.assertEqual(loan.line_ids.mapped('date'), [first, date(2027, 1, 1), date(2027, 2, 1)])
        self.assertEqual(self._money(loan), before)
        loan._validate_imported_schedule()

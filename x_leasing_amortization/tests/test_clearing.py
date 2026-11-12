from datetime import date

from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .test_early_settlement import LeasingScheduleCommon
from .test_interest_conversion import TestLeasingInterestConversion


@tagged('post_install', '-at_install')
class TestLeasingClearing(LeasingScheduleCommon):
    _converted = TestLeasingInterestConversion._converted

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.currency.rounding = 1
        cls.lessor = cls.env['res.partner'].create({'name': 'Clearing QA Lessor', 'is_company': True})
        cls.po.leasing_partner_id = cls.lessor
        cls.clearing_journal = cls.env['account.journal'].create({
            'name': 'CLEARING AP LEASING', 'code': 'CLP', 'type': 'general',
            'company_id': cls.company.id,
        })
        cls.clearing_accounts = cls.env['account.account'].create([
            {'name': label, 'code': '7960010%s' % number, 'account_type': kind,
             'company_ids': [Command.set(cls.company.ids)]}
            for number, (label, kind) in enumerate([
                ('CLEARING AP LEASING', 'asset_current'),
                ('AP DEALER ANGSURAN 1', 'liability_current'),
                ('DOWN PAYMENT', 'asset_prepayments'),
            ], 1)
        ])

    def _clearing_loan(self, **values):
        return self._converted(**{
            'total_hutang': 544770000, 'harga_otr': 605300000,
            'down_payment_leasing': 60530000, 'duration': 48,
            'quoted_interest_rate': 4.6404, 'due_date': date(2026, 1, 21),
            'clearing_journal_id': self.clearing_journal.id,
            'clearing_account_id': self.clearing_accounts[0].id,
            'clearing_first_installment_account_id': self.clearing_accounts[1].id,
            'clearing_down_payment_account_id': self.clearing_accounts[2].id,
            **values,
        })

    def _clearing(self, loan):
        action = loan.action_create_leasing_clearing()
        self.assertEqual(action['res_model'], 'account.move')
        return self.env['account.move'].browse(action['res_id'])

    def _source_snapshot(self, loan):
        return loan.line_ids.read(['date', 'principal', 'interest', 'payment',
                                   'outstanding_balance', 'vendor_bill_id', 'payment_date',
                                   'generated_move_ids', 'monthly_adjustment_move_id'])

    def test_four_draft_lines_match_screenshot_and_do_not_change_schedule(self):
        loan = self._clearing_loan(leasing_installment=13456000)
        before = self._source_snapshot(loan)
        move = self._clearing(loan)
        self.assertEqual(move.state, 'draft')
        self.assertEqual(move.auto_post, 'no')
        self.assertEqual(move.move_type, 'entry')
        self.assertEqual(move.journal_id, self.clearing_journal)
        self.assertEqual(move.date, date(2026, 1, 21))
        self.assertEqual(move.ref, '%s - %s' % (self.po.name, loan.name))
        self.assertEqual(move.line_ids.mapped('debit'), [605300000, 0, 0, 0])
        self.assertEqual(move.line_ids.mapped('credit'), [0, 531314000, 13456000, 60530000])
        self.assertEqual(move.line_ids.mapped('partner_id'), self.lessor | self.vendor)
        items = move.line_ids.sorted('id')
        self.assertEqual(items[:2].partner_id, self.lessor)
        self.assertEqual(items[2:].partner_id, self.vendor)
        self.assertEqual(items.mapped('account_id'),
                         self.clearing_accounts[0] | self.principal_account | self.clearing_accounts[1:])
        self.assertEqual(items.mapped('name'),
                         ['CLEARING AP LEASING', 'AP LEASING', 'AP DEALER ANGSURAN 1', 'DOWN PAYMENT'])
        self.assertFalse(items.tax_ids)
        self.assertTrue(all(item.analytic_distribution == {str(self.analytic.id): 100} for item in items))
        self.assertEqual(loan.clearing_move_count, 1)
        self.assertTrue(loan.has_active_clearing_move)
        self.assertEqual(self._source_snapshot(loan), before)
        self.assertFalse(move.is_loan_payment_move)

    def test_manual_installment_takes_precedence_over_conversion_quote(self):
        loan = self._clearing_loan(leasing_installment=13456000)
        self.assertEqual(loan.conversion_installment_preview, 13456001)
        move = self._clearing(loan)
        self.assertEqual(move.line_ids.filtered(lambda line: line.name == 'AP DEALER ANGSURAN 1').credit,
                         loan.leasing_installment)

    def test_without_manual_uses_conversion_quote(self):
        loan = self._clearing_loan()
        self.assertFalse(loan.leasing_installment)
        self.assertEqual(loan.conversion_installment_preview, 13456001)
        move = self._clearing(loan)
        self.assertEqual(move.line_ids.filtered(lambda line: line.name == 'AP DEALER ANGSURAN 1').credit, 13456001)
        self.assertEqual(move.line_ids.filtered(lambda line: line.name == 'AP LEASING').credit, 531313999)

    def test_review_and_native_post_keep_payment_and_accrual_links_unchanged(self):
        loan = self._clearing_loan(leasing_installment=13456000)
        loan.action_confirm()
        before = self._source_snapshot(loan)
        move = self._clearing(loan)
        move.action_post()
        self.assertEqual(move.state, 'posted')
        self.assertTrue(move.name.startswith('CLP/2026/01/'))
        self.assertEqual(sum(move.line_ids.mapped('balance')), 0)
        self.assertEqual(self._source_snapshot(loan), before)
        self.assertEqual(loan.state, 'running')

    def test_repeated_click_reuses_draft_and_posted_entry(self):
        loan = self._clearing_loan()
        move = self._clearing(loan)
        self.assertEqual(self._clearing(loan), move)
        move.action_post()
        self.assertEqual(self._clearing(loan), move)
        self.assertEqual(loan.clearing_move_count, 1)

    def test_two_unit_schedules_of_same_po_create_separate_clearings(self):
        first = self._clearing_loan()
        second = self._clearing_loan()
        first_move = self._clearing(first)
        second_move = self._clearing(second)
        self.assertEqual(first.purchase_order_id, second.purchase_order_id)
        self.assertNotEqual(first_move, second_move)
        self.assertNotEqual(first_move.ref, second_move.ref)
        self.assertEqual(first_move.leasing_clearing_loan_id, first)
        self.assertEqual(second_move.leasing_clearing_loan_id, second)

    def test_cancelled_draft_can_be_replaced_but_old_entry_cannot_be_reposted(self):
        loan = self._clearing_loan()
        old = self._clearing(loan)
        old.button_cancel()
        self.assertFalse(loan.has_active_clearing_move)
        new = self._clearing(loan)
        self.assertNotEqual(new, old)
        self.assertEqual(loan.clearing_move_count, 2)
        old.button_draft()
        with self.assertRaisesRegex(UserError, 'Clearing aktif lain'), self.env.cr.savepoint():
            old.action_post()
        self.assertEqual(new.state, 'draft')

    def test_addb_and_noneligible_statuses_rejected(self):
        addb = self._clearing_loan(advarr='in_arrears')
        with self.assertRaisesRegex(UserError, 'hanya untuk ADDM'):
            self._clearing(addb)
        for state in ('closed', 'cancelled'):
            loan = self._clearing_loan()
            loan.state = state
            with self.assertRaisesRegex(UserError, 'hanya untuk ADDM'):
                self._clearing(loan)
            self.assertFalse(loan.clearing_move_ids)

    def test_missing_compute_or_stale_schedule_creates_no_journal(self):
        loan = self._clearing_loan(compute=False)
        with self.assertRaises(UserError):
            self._clearing(loan)
        self.assertFalse(loan.clearing_move_ids)
        loan.action_compute_amortization_schedule()
        loan.quoted_interest_rate = 6
        with self.assertRaises(UserError):
            self._clearing(loan)
        self.assertFalse(loan.clearing_move_ids)

    def test_missing_po_or_lessor_is_not_replaced_by_manual_bank(self):
        loan = self._clearing_loan()
        loan.bank_id = self.vendor
        self.po.leasing_partner_id = False
        with self.assertRaisesRegex(UserError, 'Leasing Partner'):
            self._clearing(loan)
        self.assertFalse(loan.clearing_move_ids)
        self.po.leasing_partner_id = self.lessor
        loan = self._loan(count=2, state='draft', advarr='in_advance_addm', purchase_order_id=False)
        with self.assertRaisesRegex(UserError, 'Purchase Order'):
            self._clearing(loan)

    def test_po_partners_are_used_instead_of_manual_loan_bank_and_vendor(self):
        loan = self._clearing_loan()
        manual = self.env['res.partner'].create({'name': 'Not the Clearing recipient', 'is_company': True})
        loan.write({'bank_id': manual.id, 'vendor_id': manual.id})
        move = self._clearing(loan)
        self.assertEqual(move.line_ids.sorted('id')[:2].partner_id, self.lessor)
        self.assertEqual(move.line_ids.sorted('id')[2:].partner_id, self.vendor)

    def test_missing_accounts_and_wrong_journal_are_rejected(self):
        loan = self._clearing_loan(clearing_account_id=False)
        with self.assertRaisesRegex(UserError, 'Lengkapi Jurnal Clearing'):
            self._clearing(loan)
        loan.write({'clearing_account_id': self.clearing_accounts[0].id,
                    'clearing_journal_id': self.purchase_journal.id})
        with self.assertRaisesRegex(UserError, 'Pilih jurnal Miscellaneous'):
            self._clearing(loan)
        self.assertFalse(loan.clearing_move_ids)

    def test_inactive_account_and_foreign_company_mapping_are_rejected(self):
        loan = self._clearing_loan()
        self.clearing_accounts[0].active = False
        with self.assertRaisesRegex(UserError, 'Akun Clearing harus aktif'):
            self._clearing(loan)
        self.clearing_accounts[0].active = True
        other = self.env['res.company'].create({'name': 'Foreign Clearing QA', 'company_code': 'FCLP'})
        foreign = self.env['account.account'].create({
            'name': 'Foreign Clearing', 'code': '79600301', 'account_type': 'asset_current',
            'company_ids': [Command.set(other.ids)],
        })
        loan.clearing_account_id = foreign
        with self.assertRaises(UserError):
            self._clearing(loan)
        self.assertFalse(loan.clearing_move_ids)

    def test_post_revalidates_changed_po_partner_without_modifying_existing_entry(self):
        loan = self._clearing_loan()
        move = self._clearing(loan)
        before = move.line_ids.read(['balance', 'partner_id', 'account_id'])
        self.po.leasing_partner_id = self.vendor
        with self.assertRaisesRegex(UserError, 'Header jurnal Clearing berbeda'):
            move.action_post()
        self.assertEqual(move.state, 'draft')
        self.assertEqual(move.line_ids.read(['balance', 'partner_id', 'account_id']), before)

    def test_post_rejects_balanced_manual_amount_or_tax_edits(self):
        loan = self._clearing_loan()
        move = self._clearing(loan)
        debit, credit = move.line_ids.sorted('id')[:2]
        move.write({'line_ids': [Command.update(debit.id, {'debit': debit.debit + 10}),
                                 Command.update(credit.id, {'credit': credit.credit + 10})]})
        with self.assertRaisesRegex(UserError, 'Baris jurnal Clearing berbeda'):
            move.action_post()
        self.assertEqual(move.state, 'draft')

    def test_active_clearing_freezes_config_and_schedule_recompute(self):
        loan = self._clearing_loan()
        self._clearing(loan)
        with self.assertRaisesRegex(UserError, 'Pengaturan Clearing hanya'):
            loan.clearing_account_id = self.principal_account
        with self.assertRaises(UserError):
            loan.action_compute_amortization_schedule()
        with self.assertRaises(UserError):
            loan.leasing_installment = 14000000

    def test_cancelled_clearing_allows_config_correction(self):
        loan = self._clearing_loan()
        move = self._clearing(loan)
        move.button_cancel()
        loan.clearing_account_id = self.expense_account
        replacement = self._clearing(loan)
        self.assertEqual(replacement.line_ids.sorted('id')[0].account_id, self.expense_account)

    def test_exact_manual_reference_duplicate_requires_review(self):
        loan = self._clearing_loan()
        values = loan._prepare_leasing_clearing_move()
        values.pop('leasing_clearing_loan_id')
        manual = self.env['account.move'].create(values)
        with self.assertRaisesRegex(UserError, 'referensi Clearing yang sama'):
            self._clearing(loan)
        self.assertFalse(loan.clearing_move_ids)
        self.assertEqual(manual.state, 'draft')

    def test_link_is_protected_and_not_copied_to_manual_journal(self):
        loan = self._clearing_loan()
        values = loan._prepare_leasing_clearing_move()
        with self.assertRaisesRegex(UserError, 'Gunakan tombol Clearing'):
            self.env['account.move'].create(values)
        move = self._clearing(loan)
        with self.assertRaisesRegex(UserError, 'tidak dapat diubah'):
            move.leasing_clearing_loan_id = False
        copied = move.copy()
        self.assertFalse(copied.leasing_clearing_loan_id)
        self.assertEqual(loan.clearing_move_count, 1)

    def test_zero_dp_keeps_four_lines_and_balances(self):
        loan = self._clearing_loan(down_payment_leasing=0, harga_otr=544770000)
        move = self._clearing(loan)
        self.assertEqual(len(move.line_ids), 4)
        self.assertEqual(move.line_ids.sorted('id')[-1].credit, 0)
        move.action_post()
        self.assertEqual(move.state, 'posted')

    def test_due_date_change_second_period_does_not_change_clearing_accounting_date(self):
        loan = self._clearing_loan()
        loan.action_confirm()
        move = self._clearing(loan)
        loan.second_installment_due_date = date(2026, 3, 1)
        loan.action_apply_second_installment_due_date()
        self.assertEqual(move.date, date(2026, 1, 21))
        move.action_post()
        self.assertEqual(move.state, 'posted')

    def test_nonaccounting_user_cannot_call_action(self):
        loan = self._clearing_loan()
        user = new_test_user(self.env, login='clearing_readonly', groups='base.group_user,fleet.fleet_group_user')
        with self.assertRaises(AccessError):
            loan.with_user(user).action_create_leasing_clearing()

    def test_accounting_user_can_create_without_sudo(self):
        loan = self._clearing_loan()
        user = new_test_user(self.env, login='clearing_accountant', groups='account.group_account_invoice')
        action = loan.with_user(user).action_create_leasing_clearing()
        move = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(move.create_uid, user)
        self.assertEqual(move.state, 'draft')

    def test_draft_loan_can_be_confirmed_after_clearing_creation(self):
        loan = self._clearing_loan()
        move = self._clearing(loan)
        loan.action_confirm()
        self.assertEqual(loan.state, 'running')
        self.assertEqual(move.state, 'draft')
        move.action_post()
        self.assertEqual(move.state, 'posted')

    def test_payable_dealer_account_has_partner_and_maturity(self):
        loan = self._clearing_loan(clearing_first_installment_account_id=self.payable_account.id)
        move = self._clearing(loan)
        item = move.line_ids.filtered(lambda line: line.name == 'AP DEALER ANGSURAN 1')
        self.assertEqual(item.partner_id, self.vendor)
        self.assertEqual(item.date_maturity, date(2026, 1, 21))
        move.action_post()
        self.assertEqual(move.state, 'posted')

    def test_unbalanced_historical_schedule_does_not_force_balancing_line(self):
        loan = self._loan(count=2, state='draft', advarr='in_advance_addm')
        loan.write({
            'harga_otr': 605300000, 'down_payment_leasing': 60530000,
            'clearing_journal_id': self.clearing_journal.id,
            'clearing_account_id': self.clearing_accounts[0].id,
            'clearing_first_installment_account_id': self.clearing_accounts[1].id,
            'clearing_down_payment_account_id': self.clearing_accounts[2].id,
        })
        with self.assertRaisesRegex(UserError, 'Clearing tidak seimbang'):
            self._clearing(loan)
        self.assertFalse(loan.clearing_move_ids)

    def test_empty_header_tax_payload_on_clearing_is_harmless(self):
        if 'header_tax_ids' not in self.env['account.move']._fields:
            self.skipTest('Optional invoice header taxes addon not installed')
        loan = self._clearing_loan()
        move = self._clearing(loan)
        before = move.line_ids.read(['balance', 'account_id', 'partner_id', 'analytic_distribution'])
        move.write({'header_tax_ids': [Command.clear()]})
        move.action_post()
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.line_ids.read(['balance', 'account_id', 'partner_id', 'analytic_distribution']), before)

    def test_native_form_has_addm_button_smart_button_and_loan_settings(self):
        view = self.env.ref('x_leasing_amortization.account_loan_form_inherit_leasing')
        arch = etree.fromstring(self.env['account.loan'].get_view(view_id=view.id, view_type='form')['arch'])
        buttons = arch.xpath("//header/button[@name='action_create_leasing_clearing']")
        self.assertEqual(len(buttons), 1)
        self.assertIn("advarr != 'in_advance_addm'", buttons[0].get('invisible'))
        source = etree.fromstring(self.env.ref('x_leasing_amortization.account_loan_form_clearing').arch_db)
        self.assertEqual(source.xpath("//button[@name='action_create_leasing_clearing']")[0].get('groups'),
                         'account.group_account_invoice')
        for name in ('clearing_journal_id', 'clearing_account_id',
                     'clearing_first_installment_account_id', 'clearing_down_payment_account_id'):
            self.assertEqual(len(arch.xpath("//page[@name='main_page']//field[@name='%s']" % name)), 1)
        self.assertEqual(len(arch.xpath("//button[@name='action_view_leasing_clearing']")), 1)

    def test_cancel_or_set_to_draft_requires_clearing_review_first(self):
        loan = self._clearing_loan()
        move = self._clearing(loan)
        for method in (loan.action_cancel, loan.action_set_to_draft):
            with self.assertRaisesRegex(UserError, 'jurnal Clearing aktif'):
                method()
        self.assertEqual(move.state, 'draft')
        self.assertEqual(loan.state, 'draft')
        move.button_cancel()
        loan.action_cancel()
        self.assertEqual(loan.state, 'cancelled')

    def test_fleet_readonly_form_does_not_request_accounting_only_flags(self):
        user = new_test_user(self.env, login='clearing_fleet_view', groups='base.group_user,fleet.fleet_group_user')
        view = self.env.ref('x_leasing_amortization.account_loan_form_inherit_leasing')
        arch = etree.fromstring(self.env['account.loan'].with_user(user).get_view(
            view_id=view.id, view_type='form')['arch'])
        self.assertFalse(arch.xpath("//button[@name='action_create_leasing_clearing']"))
        self.assertFalse(arch.xpath("//field[@name='has_active_clearing_move']"))

    def test_history_action_checks_move_read_access_for_multiple_records(self):
        loan = self._clearing_loan()
        first = self._clearing(loan)
        first.button_cancel()
        second = self._clearing(loan)
        action = loan.action_view_leasing_clearing()
        self.assertEqual(set(action['domain'][0][2]), {first.id, second.id})
        user = new_test_user(self.env, login='clearing_history_denied', groups='base.group_user,fleet.fleet_group_user')
        with self.assertRaises(AccessError):
            loan.with_user(user).action_view_leasing_clearing()

    def test_historical_effective_schedule_also_protects_reset_and_compute(self):
        loan = self._loan(count=2, state='draft', advarr='in_advance_addm',
                          line_ids=[Command.create({'date': date(2026, 1, 21), 'principal': 100, 'interest': 0}),
                                    Command.create({'date': date(2026, 2, 21), 'principal': 900, 'interest': 100})])
        loan.write({
            'total_hutang': 1000, 'amount_borrowed': 1000, 'harga_otr': 1500, 'down_payment_leasing': 500,
            'clearing_journal_id': self.clearing_journal.id,
            'clearing_account_id': self.clearing_accounts[0].id,
            'clearing_first_installment_account_id': self.clearing_accounts[1].id,
            'clearing_down_payment_account_id': self.clearing_accounts[2].id,
        })
        move = self._clearing(loan)
        before = self._source_snapshot(loan)
        for method in (loan.action_reset, loan.action_compute_amortization_schedule):
            with self.assertRaisesRegex(UserError, 'jurnal Clearing tidak boleh'):
                method()
        self.assertEqual(self._source_snapshot(loan), before)
        move.action_post()
        self.assertEqual(move.state, 'posted')

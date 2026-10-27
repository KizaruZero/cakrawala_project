from datetime import date

from dateutil.relativedelta import relativedelta
from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestLeasingEarlySettlement(TransactionCase):
    """Native draft Vendor Bills, with no recomputation of the leasing schedule."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={**cls.env.context, 'tracking_disable': True, 'tz': 'Asia/Jakarta'})
        cls.company = cls.env.company
        cls.company.company_code = 'ETEST'
        cls.currency = cls.env.ref('base.IDR')
        cls.currency.active = True
        cls.company.currency_id = cls.currency
        cls.company.account_fiscal_country_id = cls.env.ref('base.id')
        cls.tax_group = cls.env['account.tax.group'].create({
            'name': 'ET Tax Group', 'company_id': cls.company.id,
            'country_id': cls.env.ref('base.id').id,
        })

        def account(name, code, kind, **extra):
            return cls.env['account.account'].create({
                'name': name, 'code': code, 'account_type': kind,
                'company_ids': [Command.set(cls.company.ids)], **extra,
            })

        cls.principal_account = account('ET Principal', '79600001', 'liability_non_current')
        cls.payable_account = account('ET Vendor Payable', '79600002', 'liability_payable', reconcile=True)
        cls.cash_account = account('ET Bank', '79600003', 'asset_cash')
        cls.expense_account = account('ET Interest Expense', '79600004', 'expense')
        cls.accrued_account = account('ET Accrued Interest', '79600005', 'liability_current')
        cls.general_journal = cls.env['account.journal'].create({
            'name': 'ET General', 'code': 'ETGEN', 'type': 'general', 'company_id': cls.company.id,
        })
        cls.purchase_journal = cls.env['account.journal'].create({
            'name': 'ET Vendor Bills', 'code': 'ETBIL', 'type': 'purchase',
            'company_id': cls.company.id, 'default_account_id': cls.expense_account.id,
        })
        cls.bank_journal = cls.env['account.journal'].create({
            'name': 'ET Bank', 'code': 'ETBNK', 'type': 'bank',
            'company_id': cls.company.id, 'default_account_id': cls.cash_account.id,
        })
        cls.term = cls.env['account.payment.term'].create({
            'name': 'ET Vendor 30 Days', 'company_id': cls.company.id,
            'line_ids': [Command.create({'value': 'percent', 'value_amount': 100, 'nb_days': 30})],
        })
        cls.vendor = cls.env['res.partner'].create({
            'name': 'ET Leasing Vendor', 'is_company': True,
            'property_account_payable_id': cls.payable_account.id,
            'property_supplier_payment_term_id': cls.term.id,
        })
        cls.plan = cls.env['account.analytic.plan'].create({'name': 'ET Vehicles'})
        cls.analytic = cls.env['account.analytic.account'].create({
            'name': 'ET B 95 KKJ', 'plan_id': cls.plan.id, 'company_id': cls.company.id,
        })
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'ET Brand'})
        model = cls.env['fleet.vehicle.model'].create({'name': 'ET Model', 'brand_id': brand.id})
        cls.vehicle = cls.env['fleet.vehicle'].create({
            'model_id': model.id, 'license_plate': 'B 95 KKJ',
            'company_id': cls.company.id, 'analytic_account_id': cls.analytic.id,
        })
        cls.po = cls.env['purchase.order'].create({
            'partner_id': cls.vendor.id, 'leasing_partner_id': cls.vendor.id,
            'company_id': cls.company.id, 'leasing_agreement': 'AGR-ET-001',
        })

    def _loan(self, count=48, **extra):
        principals = [6000000.0] * count
        if count >= 14:
            principals[12] = 5826677.43
            principals[13] = 5870412.07
        loan = self.env['account.loan'].create({
            'name': 'ET Schedule', 'company_id': self.company.id,
            'date': date(2025, 11, 1), 'start_date_leasing': date(2025, 11, 1),
            'purchase_order_id': self.po.id, 'vehicle_id': self.vehicle.id,
            'duration': count, 'state': 'running',
            'long_term_account_id': self.principal_account.id,
            'short_term_account_id': self.accrued_account.id,
            'expense_account_id': self.expense_account.id,
            'accrued_interest_account_id': self.accrued_account.id,
            'journal_id': self.general_journal.id,
            'line_ids': [Command.create({
                'date': date(2025, 11, 1) + relativedelta(months=index, day=31),
                'principal': principal, 'interest': 1755400.32,
            }) for index, principal in enumerate(principals)],
            **extra,
        })
        loan.write({'vendor_id': self.vendor.id, 'total_hutang': sum(principals),
                    'amount_borrowed': sum(principals)})
        return loan

    def _entry(self, line, state='posted', native=False, accrued=False):
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.general_journal.id,
            'company_id': self.company.id, 'date': date(2026, 10, 27),
            'generating_loan_line_id': line.id if native else False,
            'is_loan_payment_move': native,
            'line_ids': [
                Command.create({'name': 'ET Principal', 'account_id': self.principal_account.id,
                                'debit': line.principal}),
                Command.create({'name': 'ET Bank', 'account_id': self.cash_account.id,
                                'credit': line.principal}),
            ],
        })
        if state == 'posted':
            move.action_post()
        elif state == 'cancel':
            move.button_cancel()
        if accrued:
            line.monthly_adjustment_move_id = move
        elif not native:
            line.vendor_bill_id = move
        return move

    def _bill(self, loan):
        action = loan.action_create_early_settlement_bill()
        self.assertEqual(action['res_model'], 'account.move')
        return self.env['account.move'].browse(action['res_id'])

    def _snapshot(self, loan):
        return (
            loan.read(['state', 'amount_borrowed', 'interest', 'duration', 'monthly_installment',
                       'total_installment_payment', 'total_bunga', 'outstanding_balance'])[0],
            loan.line_ids.read(['date', 'principal', 'interest', 'payment', 'vendor_bill_id',
                                'payment_date', 'monthly_adjustment_move_id']),
        )

    def test_installments_14_through_48_create_35_principal_only_lines(self):
        loan = self._loan()
        posted = self._entry(loan.line_ids[12])
        before = self._snapshot(loan)
        bill = self._bill(loan)
        self.assertEqual(bill.state, 'draft')
        self.assertEqual(bill.move_type, 'in_invoice')
        self.assertEqual(bill.partner_id, self.vendor)
        self.assertEqual(bill.company_id, self.company)
        self.assertEqual(bill.currency_id, self.currency)
        self.assertEqual(bill.invoice_date, fields.Date.context_today(loan))
        self.assertEqual(bill.invoice_payment_term_id, self.term)
        self.assertEqual(bill.early_settlement_loan_id, loan)
        self.assertEqual(len(bill.invoice_line_ids), 35)
        first, last = bill.invoice_line_ids[0], bill.invoice_line_ids[-1]
        self.assertEqual(first.name, 'Angsuran ke 14 - AGR-ET-001 - B 95 KKJ')
        self.assertEqual(first.price_unit, 5870412.07)
        self.assertEqual(last.name, 'Angsuran ke 48 - AGR-ET-001 - B 95 KKJ')
        self.assertEqual(bill.invoice_line_ids.early_settlement_schedule_line_id, loan.line_ids[13:])
        for line in bill.invoice_line_ids:
            self.assertEqual(line.quantity, 1)
            self.assertEqual(line.account_id, self.principal_account)
            self.assertFalse(line.product_id)
            self.assertFalse(line.tax_ids)
            self.assertEqual(line.discount, 0)
            self.assertEqual(line.analytic_distribution, {str(self.analytic.id): 100})
            self.assertEqual(line.price_unit, line.early_settlement_schedule_line_id.principal)
        self.assertAlmostEqual(bill.amount_total, sum(loan.line_ids[13:].mapped('principal')), places=2)
        self.assertEqual(bill.amount_tax, 0)
        self.assertEqual(before, self._snapshot(loan))
        self.assertEqual(posted.state, 'posted')

    def test_cutoff_is_last_posted_not_posted_count_and_accrual_does_not_count(self):
        loan = self._loan()
        self._entry(loan.line_ids[2])
        self._entry(loan.line_ids[12])
        self._entry(loan.line_ids[24], accrued=True)
        bill = self._bill(loan)
        self.assertEqual(bill.invoice_line_ids[0].early_settlement_schedule_line_id, loan.line_ids[13])
        self.assertEqual(len(bill.invoice_line_ids), 35)

    def test_native_posted_payment_is_also_a_cutoff(self):
        loan = self._loan(count=4)
        self._entry(loan.line_ids[1], native=True)
        bill = self._bill(loan)
        self.assertEqual(bill.invoice_line_ids.early_settlement_schedule_line_id, loan.line_ids[2:])

    def test_no_posted_payments_uses_all_installments(self):
        loan = self._loan(count=3)
        self.assertEqual(len(self._bill(loan).invoice_line_ids), 3)

    def test_all_installments_posted_has_no_remaining_bill(self):
        loan = self._loan(count=3)
        self._entry(loan.line_ids[-1])
        with self.assertRaisesRegex(UserError, 'Tidak ada sisa angsuran'):
            self._bill(loan)
        self.assertFalse(loan.early_settlement_bill_ids)

    def test_draft_payment_in_tail_blocks_without_overwriting(self):
        loan = self._loan(count=4)
        self._entry(loan.line_ids[0])
        original = self._entry(loan.line_ids[2], state='draft')
        with self.assertRaisesRegex(UserError, 'sudah memiliki jurnal pembayaran'):
            self._bill(loan)
        self.assertEqual(loan.line_ids[2].vendor_bill_id, original)
        self.assertFalse(loan.early_settlement_bill_ids)

    def test_cancelled_payment_in_tail_does_not_block(self):
        loan = self._loan(count=4)
        original = self._entry(loan.line_ids[1], state='cancel')
        bill = self._bill(loan)
        self.assertEqual(len(bill.invoice_line_ids), 4)
        self.assertEqual(loan.line_ids[1].vendor_bill_id, original)

    def test_repeat_click_reopens_same_draft(self):
        loan = self._loan(count=3)
        first = self._bill(loan)
        self.env.invalidate_all()
        second = self._bill(loan)
        self.assertEqual(first, second)
        self.assertEqual(loan.early_settlement_bill_count, 1)

    def test_cancelled_bill_allows_new_bill_and_keeps_history(self):
        loan = self._loan(count=3)
        first = self._bill(loan)
        first.button_cancel()
        second = self._bill(loan)
        self.assertNotEqual(first, second)
        self.assertEqual(first.state, 'cancel')
        self.assertEqual(second.state, 'draft')
        self.assertEqual(loan.early_settlement_bill_count, 2)

    def test_deleted_draft_allows_regeneration(self):
        loan = self._loan(count=3)
        first = self._bill(loan)
        first.unlink()
        second = self._bill(loan)
        self.assertEqual(second.state, 'draft')
        self.assertEqual(loan.early_settlement_bill_count, 1)

    def test_posted_bill_reopens_without_closing_or_recomputing_loan(self):
        loan = self._loan(count=4)
        self._entry(loan.line_ids[0])
        before = self._snapshot(loan)
        bill = self._bill(loan)
        bill.action_post()
        self.assertEqual(bill.state, 'posted')
        self.assertEqual(bill.payment_state, 'not_paid')
        self.assertEqual(self._bill(loan), bill)
        self.assertEqual(before, self._snapshot(loan))
        principal_debit = sum(bill.line_ids.filtered(
            lambda line: line.account_id == self.principal_account).mapped('debit'))
        payable_credit = sum(bill.line_ids.filtered(
            lambda line: line.account_id == self.payable_account).mapped('credit'))
        self.assertEqual(principal_debit, bill.amount_total)
        self.assertEqual(payable_credit, bill.amount_total)

    def test_bill_copy_does_not_inherit_settlement_links(self):
        bill = self._bill(self._loan(count=2))
        duplicate = bill.copy()
        self.assertFalse(duplicate.early_settlement_loan_id)
        self.assertFalse(duplicate.invoice_line_ids.early_settlement_schedule_line_id)

    def test_non_running_states_block_even_direct_rpc(self):
        for state in ['draft', 'closed', 'cancelled']:
            with self.subTest(state=state):
                loan = self._loan(count=2, state=state)
                with self.assertRaisesRegex(UserError, 'Running'):
                    self._bill(loan)

    def test_missing_vendor_and_account_are_actionable(self):
        loan = self._loan(count=2)
        loan.vendor_id = False
        with self.assertRaisesRegex(UserError, 'Vendor leasing'):
            self._bill(loan)
        loan.vendor_id = self.vendor
        loan.long_term_account_id = False
        with self.assertRaisesRegex(UserError, 'Hutang Pokok'):
            self._bill(loan)

    def test_payable_principal_account_rejected_before_native_invoice_error(self):
        loan = self._loan(count=2)
        loan.long_term_account_id = self.payable_account
        with self.assertRaisesRegex(UserError, 'kewajiban non-Payable'):
            self._bill(loan)
        self.assertFalse(loan.early_settlement_bill_ids)

    def test_missing_purchase_journal_does_not_fall_back_to_general(self):
        loan = self._loan(count=2)
        self.env['account.journal'].search([
            ('company_id', '=', self.company.id), ('type', '=', 'purchase')]).active = False
        with self.assertRaisesRegex(UserError, 'jurnal Vendor Bills'):
            self._bill(loan)

    def test_zero_and_negative_remaining_principal_rejected(self):
        loan = self._loan(count=2)
        loan.line_ids.principal = 0
        with self.assertRaisesRegex(UserError, 'lebih besar dari nol'):
            self._bill(loan)
        loan.line_ids[0].principal = -1
        with self.assertRaisesRegex(UserError, 'tidak boleh negatif'):
            self._bill(loan)

    def test_regular_payment_wizard_cannot_double_pay_settlement_lines(self):
        loan = self._loan(count=3)
        bill = self._bill(loan)
        wizard = self.env['leasing.payment.wizard'].with_context(active_ids=loan.line_ids.ids).create({
            'journal_id': self.bank_journal.id, 'payment_date': date(2026, 10, 27),
        })
        with self.assertRaisesRegex(UserError, 'sudah tercakup'):
            wizard.action_confirm_payment()
        self.assertFalse(loan.line_ids.vendor_bill_id)
        bill.button_cancel()
        wizard.action_confirm_payment()
        self.assertEqual(loan.line_ids.vendor_bill_id.state, 'posted')

    def test_posting_rejects_source_principal_changed_since_draft(self):
        loan = self._loan(count=2)
        bill = self._bill(loan)
        loan.line_ids[0].principal += 100
        with self.assertRaisesRegex(UserError, 'pokok angsuran asli'):
            bill.action_post()
        self.assertEqual(bill.state, 'draft')

    def test_posting_rejects_new_payment_after_bill_was_created(self):
        loan = self._loan(count=3)
        bill = self._bill(loan)
        self._entry(loan.line_ids[0])
        with self.assertRaisesRegex(UserError, 'tidak lagi sesuai'):
            bill.action_post()
        self.assertEqual(bill.state, 'draft')

    def test_posting_rejects_quantity_discount_or_extra_item(self):
        loan = self._loan(count=2)
        bill = self._bill(loan)
        line = bill.invoice_line_ids[0]
        for vals in [{'quantity': 2}, {'quantity': 1, 'discount': 10}]:
            line.write(vals)
            with self.assertRaisesRegex(UserError, 'pokok angsuran asli'):
                bill.action_post()
        line.discount = 0
        bill.invoice_line_ids = [Command.create({
            'name': 'Unrequested fee', 'account_id': self.expense_account.id,
            'quantity': 1, 'price_unit': 100, 'tax_ids': [Command.clear()],
        })]
        with self.assertRaisesRegex(UserError, 'tidak lagi sesuai'):
            bill.action_post()

    def test_unauthorized_user_cannot_create_bill(self):
        loan = self._loan(count=2)
        fleet_user = new_test_user(self.env, login='et_fleet_only', groups='fleet.fleet_group_user')
        with self.assertRaises(AccessError):
            loan.with_user(fleet_user).action_create_early_settlement_bill()
        self.assertFalse(loan.early_settlement_bill_ids)

    def test_cross_company_access_is_not_escalated(self):
        loan = self._loan(count=2)
        other = self.env['res.company'].create({'name': 'ET Other Company', 'company_code': 'ETOTHER'})
        user = new_test_user(self.env, login='et_other_company', groups='account.group_account_manager',
                             company_id=other.id, company_ids=[Command.set(other.ids)])
        with self.assertRaises(AccessError):
            loan.with_user(user).with_context(allowed_company_ids=other.ids).action_create_early_settlement_bill()

    def test_native_form_contains_running_button_and_bill_smart_button(self):
        arch = etree.fromstring(self.env['account.loan'].get_view(
            view_id=self.env.ref('account_loans.account_loan_form_view').id, view_type='form')['arch'])
        button = arch.xpath("//header/button[@name='action_create_early_settlement_bill']")
        self.assertEqual(len(button), 1)
        self.assertEqual(button[0].get('string'), 'Pelunasan Dipercepat')
        self.assertEqual(button[0].get('invisible'), "state != 'running'")
        self.assertTrue(arch.xpath("//button[@name='action_view_early_settlement_bills']"))
        bill_arch = etree.fromstring(self.env['account.move'].get_view(
            view_id=self.env.ref('account.view_move_form').id, view_type='form')['arch'])
        self.assertTrue(bill_arch.xpath("//field[@name='early_settlement_loan_id']"))

    def test_bill_traceability_survives_reload(self):
        loan = self._loan(count=3)
        bill = self._bill(loan)
        self.env.invalidate_all()
        self.assertEqual(loan.action_view_early_settlement_bills()['res_id'], bill.id)
        self.assertEqual(bill.invoice_line_ids.early_settlement_schedule_line_id, loan.line_ids)

    def test_invoicing_user_can_generate_without_account_manager_or_sudo(self):
        loan = self._loan(count=2)
        user = new_test_user(self.env, login='et_invoicing_only', groups='account.group_account_invoice',
                             company_id=self.company.id, company_ids=[Command.set(self.company.ids)])
        action = loan.with_user(user).with_context(allowed_company_ids=self.company.ids).action_create_early_settlement_bill()
        bill = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(bill.create_uid, user)
        self.assertEqual(bill.state, 'draft')

    def test_current_liability_principal_account_is_allowed(self):
        loan = self._loan(count=2)
        loan.long_term_account_id = self.accrued_account
        bill = self._bill(loan)
        self.assertEqual(bill.invoice_line_ids.account_id, self.accrued_account)
        bill.action_post()
        self.assertEqual(bill.state, 'posted')

    def test_account_default_tax_is_explicitly_excluded(self):
        tax = self.env['account.tax'].create({
            'name': 'ET Unrequested Purchase Tax', 'type_tax_use': 'purchase',
            'amount_type': 'percent', 'amount': 11, 'company_id': self.company.id,
            'tax_group_id': self.tax_group.id,
        })
        self.principal_account.tax_ids = [Command.set(tax.ids)]
        bill = self._bill(self._loan(count=2))
        self.assertFalse(bill.invoice_line_ids.tax_ids)
        self.assertEqual(bill.amount_tax, 0)

    def test_tax_added_to_draft_is_rejected_on_posting(self):
        tax = self.env['account.tax'].create({
            'name': 'ET Extra Tax', 'type_tax_use': 'purchase',
            'amount_type': 'percent', 'amount': 11, 'company_id': self.company.id,
            'tax_group_id': self.tax_group.id,
        })
        bill = self._bill(self._loan(count=2))
        bill.invoice_line_ids[0].tax_ids = [Command.set(tax.ids)]
        with self.assertRaisesRegex(UserError, 'tanpa pajak'):
            bill.action_post()

    def test_ordinary_vendor_bill_posting_is_unchanged(self):
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.vendor.id,
            'journal_id': self.purchase_journal.id,
            'invoice_date': fields.Date.context_today(self.env['account.move']),
            'invoice_line_ids': [Command.create({
                'name': 'Ordinary bill', 'account_id': self.expense_account.id,
                'quantity': 2, 'price_unit': 12345.67, 'tax_ids': [Command.clear()],
            })],
        })
        bill.action_post()
        self.assertEqual(bill.state, 'posted')
        self.assertAlmostEqual(bill.amount_total, 24691.34, places=2)

    def test_second_active_bill_cannot_be_posted(self):
        loan = self._loan(count=2)
        first = self._bill(loan)
        second = first.copy()
        second.early_settlement_loan_id = loan
        with self.assertRaisesRegex(UserError, 'lain yang aktif'):
            second.action_post()
        self.assertEqual(first.state, 'draft')
        self.assertEqual(second.state, 'draft')

    def test_missing_agreement_uses_loan_reference_and_preserves_number(self):
        loan = self._loan(count=3, purchase_order_id=False)
        self.assertFalse(loan.agreement_no)
        self._entry(loan.line_ids[0])
        bill = self._bill(loan)
        self.assertEqual(bill.invoice_line_ids[0].name, 'Angsuran ke 2 - ET Schedule - B 95 KKJ')

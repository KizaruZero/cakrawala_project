from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.x_leasing_amortization.tests.test_early_settlement import LeasingScheduleCommon
from odoo.addons.x_leasing_amortization.tests.test_interest_conversion import TestLeasingInterestConversion


@tagged('post_install', '-at_install')
class TestLeasingVoucherPaymentPartner(LeasingScheduleCommon):
    _converted = TestLeasingInterestConversion._converted

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.approver = new_test_user(
            cls.env, login='voucher_partner_approver_qa',
            groups='account.group_account_invoice,x_payment_voucher_leasing.group_leasing_voucher_manager',
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)],
        )

    def setUp(self):
        super().setUp()
        self.lessor = self.env['res.partner'].create({'name': 'BNI Leasing Payment QA', 'is_company': True})
        self.po.leasing_partner_id = self.lessor
        self.config = self.env['leasing.voucher.config'].create({
            'company_id': self.company.id, 'require_same_partner': True,
            'layer_ids': [Command.create({'sequence': 1, 'min_amount': 0, 'approver_id': self.approver.id})],
        })

    def _voucher(self, lines, approve=False):
        action = lines.action_create_payment_voucher_leasing()
        voucher = self.env[action['res_model']].browse(action['res_id'])
        if approve:
            voucher.action_submit()
            self.env['leasing.voucher.decision'].with_user(self.approver).create({
                'voucher_id': voucher.id, 'decision': 'approve', 'remarks': 'Approved payment partner QA',
            }).action_confirm()
            self.assertEqual(voucher.state, 'approved')
        return voucher

    def _pay(self, voucher, journal=None):
        wizard = self.env['leasing.voucher.pay.wizard'].create({
            'voucher_id': voucher.id, 'journal_id': (journal or self.bank_journal).id,
            'payment_date': '2026-11-11',
        })
        wizard.action_confirm_payment()
        return voucher.line_ids.payment_move_id

    def _other_loan(self, partner=None, vendor=None):
        po = self.po.copy({
            'partner_id': (vendor or self.vendor).id,
            'leasing_partner_id': (partner or self.lessor).id,
        })
        loan = self._loan(count=2, purchase_order_id=po.id)
        if vendor:
            loan.vendor_id = vendor
        return loan

    def test_voucher_snapshots_po_leasing_partner_not_dealer_or_manual_bank(self):
        loan = self._loan(count=2, bank_id=self.vendor.id)
        voucher = self._voucher(loan.line_ids)
        self.assertEqual(voucher.partner_id, self.lessor)
        self.assertEqual(voucher.line_ids.vendor_id, self.lessor)
        self.assertEqual(voucher.partner_summary, self.lessor.display_name)
        self.assertEqual(loan.vendor_id, self.vendor)
        self.assertEqual(loan.bank_id, self.vendor)

    def test_posted_header_and_all_journal_items_use_lessor_with_same_amounts(self):
        loan = self._loan(count=2)
        lines = loan.line_ids
        before = lines.read(['date', 'principal', 'interest', 'payment', 'interest_balance'])
        amount = sum(lines.mapped('payment'))
        voucher = self._voucher(lines, approve=True)
        move = self._pay(voucher)
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.partner_id, self.lessor)
        self.assertEqual(move.line_ids.partner_id, self.lessor)
        self.assertEqual(sum(move.line_ids.mapped('debit')), amount)
        self.assertEqual(sum(move.line_ids.mapped('credit')), amount)
        bank_line = move.line_ids.filtered(lambda row: row.account_id == self.cash_account)
        self.assertEqual(bank_line.credit, amount)
        self.assertEqual(move.journal_id, self.bank_journal)
        self.assertEqual(str(move.date), '2026-11-11')
        self.assertEqual(lines.read(list(before[0])), before)
        self.assertEqual(lines.vendor_bill_id, move)
        self.assertEqual(set(lines.mapped('payment_date')), {move.date})
        self.assertEqual(loan.vendor_id, self.vendor)
        self.assertEqual(voucher.state, 'paid')

    def test_different_dealers_same_lessor_can_share_voucher(self):
        dealer = self.env['res.partner'].create({'name': 'Other Dealer QA', 'is_company': True})
        first = self._loan(count=2)
        second = self._other_loan(vendor=dealer)
        voucher = self._voucher(first.line_ids | second.line_ids, approve=True)
        self.assertEqual(voucher.partner_id, self.lessor)
        moves = self._pay(voucher)
        self.assertEqual(len(moves), 2)
        self.assertEqual(moves.partner_id, self.lessor)
        self.assertEqual(moves.line_ids.partner_id, self.lessor)

    def test_same_dealer_different_lessors_block_when_same_partner_required(self):
        other = self.env['res.partner'].create({'name': 'Other Lessor QA', 'is_company': True})
        lines = self._loan(count=2).line_ids | self._other_loan(partner=other).line_ids
        before = self.env['leasing.payment.voucher'].search_count([])
        with self.assertRaisesRegex(UserError, 'Leasing Partner yang sama'):
            self._voucher(lines)
        self.assertEqual(self.env['leasing.payment.voucher'].search_count([]), before)
        self.assertFalse(lines.leasing_voucher_id)

    def test_multiple_lessors_allowed_post_separate_moves_to_each_lessor(self):
        self.config.require_same_partner = False
        other = self.env['res.partner'].create({'name': 'Multi Lessor QA', 'is_company': True})
        first = self._loan(count=2)
        second = self._other_loan(partner=other)
        voucher = self._voucher(first.line_ids | second.line_ids, approve=True)
        self.assertFalse(voucher.partner_id)
        self.assertEqual(voucher.line_ids.vendor_id, self.lessor | other)
        self._pay(voucher)
        self.assertEqual(first.line_ids.vendor_bill_id.partner_id, self.lessor)
        self.assertEqual(second.line_ids.vendor_bill_id.partner_id, other)

    def test_empty_po_lessor_does_not_fall_back_to_vendor_or_manual_bank(self):
        self.po.leasing_partner_id = False
        loan = self._loan(count=2, bank_id=self.vendor.id)
        with self.assertRaisesRegex(UserError, 'Leasing Partner.*belum diisi'):
            self._voucher(loan.line_ids)
        self.assertFalse(loan.line_ids.leasing_voucher_id)

    def test_no_po_requires_po_leasing_partner(self):
        loan = self._loan(count=2, purchase_order_id=False, bank_id=self.lessor.id)
        with self.assertRaisesRegex(UserError, 'Leasing Partner.*belum diisi'):
            self._voucher(loan.line_ids)

    def test_changed_lessor_before_submit_requires_new_voucher(self):
        voucher = self._voucher(self._loan(count=2).line_ids)
        self.po.leasing_partner_id = self.vendor
        with self.assertRaisesRegex(UserError, 'Batalkan dan buat ulang'):
            voucher.action_submit()
        self.assertEqual(voucher.state, 'draft')
        self.assertFalse(voucher.step_ids)
        self.assertEqual(voucher.partner_id, self.lessor)

    def test_changed_lessor_during_approval_does_not_approve_different_recipient(self):
        voucher = self._voucher(self._loan(count=2).line_ids)
        voucher.action_submit()
        self.po.leasing_partner_id = self.vendor
        with self.assertRaisesRegex(UserError, 'Batalkan dan buat ulang'):
            voucher._decision('approve', 'QA')
        self.assertEqual(voucher.state, 'waiting')
        self.assertEqual(voucher.step_ids.state, 'pending')

    def test_changed_or_removed_lessor_after_approval_never_redirects_payment(self):
        voucher = self._voucher(self._loan(count=2).line_ids, approve=True)
        self.po.leasing_partner_id = self.vendor
        count = self.env['account.move'].search_count([])
        with self.assertRaisesRegex(UserError, 'Batalkan dan buat ulang'):
            self._pay(voucher)
        self.po.leasing_partner_id = False
        with self.assertRaisesRegex(UserError, 'Leasing Partner.*belum diisi'):
            self._pay(voucher)
        self.assertEqual(self.env['account.move'].search_count([]), count)
        self.assertFalse(voucher.line_ids.payment_move_id)
        self.assertEqual(voucher.state, 'approved')

    def test_cancel_and_recreate_uses_new_po_partner(self):
        lines = self._loan(count=2).line_ids
        old = self._voucher(lines, approve=True)
        self.po.leasing_partner_id = self.vendor
        old.action_cancel()
        new = self._voucher(lines, approve=True)
        self.assertEqual(new.partner_id, self.vendor)
        self.assertEqual(old.partner_id, self.lessor)
        self.assertEqual(self._pay(new).partner_id, self.vendor)

    def test_legacy_dealer_snapshot_is_not_rewritten_and_cannot_pay_other_lessor(self):
        voucher = self._voucher(self._loan(count=2).line_ids)
        voucher.write({'partner_id': self.vendor.id})
        voucher.line_ids.vendor_id = self.vendor
        # Simulate a historical already-approved voucher, not a new approval.
        voucher.state = 'approved'
        before = voucher.line_ids.read(['vendor_id', 'principal', 'interest', 'total'])
        with self.assertRaisesRegex(UserError, 'Batalkan dan buat ulang'):
            self._pay(voucher)
        self.assertEqual(voucher.line_ids.read(list(before[0])), before)
        self.assertEqual(voucher.partner_id, self.vendor)
        self.assertEqual(voucher.state, 'approved')

    def test_legacy_matching_recipient_can_still_be_paid(self):
        self.po.leasing_partner_id = self.vendor
        voucher = self._voucher(self._loan(count=2).line_ids, approve=True)
        self.assertEqual(self._pay(voucher).partner_id, self.vendor)

    def test_posted_history_stays_frozen_when_po_partner_later_changes(self):
        voucher = self._voucher(self._loan(count=2).line_ids, approve=True)
        move = self._pay(voucher)
        before = move.line_ids.read(['partner_id', 'debit', 'credit', 'balance'])
        self.po.leasing_partner_id = self.vendor
        self.assertEqual(move.partner_id, self.lessor)
        self.assertEqual(move.line_ids.read(list(before[0])), before)
        self.assertEqual(voucher.partner_id, self.lessor)
        self.assertEqual(voucher.line_ids.vendor_id, self.lessor)

    def test_repeat_payment_is_blocked_without_extra_journals(self):
        voucher = self._voucher(self._loan(count=2).line_ids, approve=True)
        self._pay(voucher)
        count = self.env['account.move'].search_count([])
        with self.assertRaises(UserError):
            self._pay(voucher)
        self.assertEqual(self.env['account.move'].search_count([]), count)

    def test_approved_recipient_and_source_snapshot_cannot_be_changed(self):
        voucher = self._voucher(self._loan(count=2).line_ids, approve=True)
        with self.assertRaisesRegex(UserError, 'Partner voucher'):
            voucher.partner_id = self.vendor
        with self.assertRaisesRegex(UserError, 'Penerima/sumber'):
            voucher.line_ids.vendor_id = self.vendor
        with self.assertRaisesRegex(UserError, 'tidak dapat dihapus'):
            voucher.line_ids.unlink()
        with self.assertRaisesRegex(UserError, 'tidak dapat ditambah'):
            voucher.line_ids[0].copy({'voucher_id': voucher.id})
        with self.assertRaisesRegex(UserError, 'tidak dapat ditambah'):
            self.env['leasing.payment.voucher.line'].with_context(default_voucher_id=voucher.id).create({
                'loan_line_id': voucher.line_ids[0].loan_line_id.id,
                'loan_id': voucher.line_ids[0].loan_id.id, 'vendor_id': self.lessor.id,
            })
        self.assertFalse(voucher.line_ids.payment_move_id)

    def test_draft_header_mismatch_cannot_be_submitted(self):
        voucher = self._voucher(self._loan(count=2).line_ids)
        voucher.partner_id = self.vendor
        with self.assertRaisesRegex(UserError, 'Partner header voucher'):
            voucher.action_submit()

    def test_reset_then_reapprove_same_recipient_can_still_be_paid(self):
        voucher = self._voucher(self._loan(count=2).line_ids, approve=True)
        voucher.action_reset()
        voucher.action_submit()
        voucher.with_user(self.approver)._decision('approve', 'Reapproved QA')
        self.assertEqual(self._pay(voucher).partner_id, self.lessor)

    def test_same_partner_policy_is_rechecked_on_submit(self):
        self.config.require_same_partner = False
        other = self.env['res.partner'].create({'name': 'Policy Change Lessor QA', 'is_company': True})
        lines = self._loan(count=2).line_ids | self._other_loan(partner=other).line_ids
        voucher = self._voucher(lines)
        self.config.require_same_partner = True
        with self.assertRaisesRegex(UserError, 'Leasing Partner yang sama'):
            voucher.action_submit()
        self.assertEqual(voucher.state, 'draft')

    def test_posting_failure_rolls_back_entire_multi_loan_payment(self):
        first, second = self._loan(count=2), self._other_loan()
        voucher = self._voucher(first.line_ids | second.line_ids, approve=True)
        model = type(self.env['account.move'])
        original = model.action_post
        calls = []

        def fail_second(moves):
            calls.append(moves.id)
            if len(calls) == 2:
                raise UserError('QA posting failure')
            return original(moves)

        count = self.env['account.move'].search_count([])
        with patch.object(model, 'action_post', fail_second):
            with self.assertRaisesRegex(UserError, 'QA posting failure'):
                self._pay(voucher)
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.env['account.move'].search_count([]), count)
        self.assertFalse(voucher.line_ids.payment_move_id)
        self.assertFalse((first | second).line_ids.vendor_bill_id)
        self.assertEqual(voucher.state, 'approved')

    def test_early_settlement_after_voucher_approval_blocks_duplicate_payment(self):
        loan = self._loan(count=2)
        voucher = self._voucher(loan.line_ids, approve=True)
        loan.action_create_early_settlement_bill()
        with self.assertRaisesRegex(UserError, 'pelunasan|Pelunasan'):
            self._pay(voucher)
        self.assertFalse(voucher.line_ids.payment_move_id)

    def test_accrued_interest_keeps_existing_vendor_source(self):
        loan = self._loan(count=2)
        move = loan.line_ids[0]._generate_monthly_adjustment_entry()
        self.assertEqual(move.partner_id, self.vendor)
        self.assertEqual(move.line_ids.partner_id, self.vendor)

    def test_converted_addm_and_addb_keep_contract_amounts_with_new_payment_partner(self):
        for advarr in ('in_advance_addm', 'in_arrears'):
            loan = self._converted(advarr=advarr)
            loan.action_confirm()
            lines = loan.line_ids[:2]
            voucher = self._voucher(lines, approve=True)
            expected = lines.filtered(lambda line: not line._is_addm_first_installment())
            self.assertEqual(voucher.line_ids.loan_line_id, expected)
            moves = self._pay(voucher)
            self.assertEqual(moves.partner_id, self.lessor)
            self.assertEqual(sum(moves.line_ids.mapped('debit')), sum(expected.mapped('payment')))

from datetime import timedelta
from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestVoucher(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref('payment_receive_voucher.group_voucher_manager')
        groups = 'account.group_account_invoice,payment_receive_voucher.group_voucher_approver'
        cls.approver = new_test_user(cls.env, login='prv_approver', groups=groups,
                                    company_id=cls.env.company.id, company_ids=[Command.set(cls.env.company.ids)])
        cls.delegate = new_test_user(cls.env, login='prv_delegate', groups=groups,
                                    company_id=cls.env.company.id, company_ids=[Command.set(cls.env.company.ids)])
        cls.config = cls.env['prv.voucher.config'].create({
            'name': 'Test Payment Approval', 'voucher_type': 'payment',
            'company_id': cls.env.company.id,
            'layer_ids': [Command.create({'sequence': 1, 'min_amount': 0, 'approver_id': cls.approver.id}),
                          Command.create({'sequence': 2, 'min_amount': 100, 'approver_id': cls.env.uid})],
        })

    def _bill(self, amount=250, kind='in_invoice', partner=None):
        move = self.env['account.move'].create({
            'move_type': kind, 'partner_id': (partner or self.partner_a).id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'name': 'Voucher test line', 'quantity': 1,
                'price_unit': amount, 'account_id': self.company_data[
                    'default_account_expense' if kind == 'in_invoice' else 'default_account_revenue'].id,
                'tax_ids': [Command.clear()]})],
        })
        move.action_post()
        return move

    def _voucher(self, moves, kind='payment'):
        return self.env['prv.voucher'].create({'voucher_type': kind, 'move_ids': [Command.set(moves.ids)]})

    def _decide(self, voucher, user, decision='approve', remarks='Approved for payment'):
        wizard = self.env['prv.voucher.decision'].with_user(user).create({
            'voucher_id': voucher.id, 'decision': decision, 'remarks': remarks})
        wizard.action_confirm()

    def test_sequential_approval_no_accounting_side_effects(self):
        bill = self._bill()
        count_moves = self.env['account.move'].search_count([])
        count_payments = self.env['account.payment'].search_count([])
        voucher = self._voucher(bill)
        with self.assertRaises(UserError):
            bill.action_register_payment()
        voucher.action_submit()
        with self.assertRaises(AccessError):
            self._decide(voucher, self.env.user)
        self._decide(voucher, self.approver)
        self.assertEqual(voucher.state, 'waiting')
        self._decide(voucher, self.env.user)
        self.assertEqual(voucher.state, 'approved')
        self.assertTrue(bill.prv_voucher_approved)
        self.assertEqual(bill.action_register_payment()['res_model'], 'account.payment.register')
        self.assertEqual(count_moves, self.env['account.move'].search_count([]))
        self.assertEqual(count_payments, self.env['account.payment'].search_count([]))

    def test_split_decision_actions_set_fixed_decision(self):
        voucher = self._voucher(self._bill())
        voucher.action_submit()
        approve_action = voucher.with_user(self.approver).action_approve()
        reject_action = voucher.with_user(self.approver).action_reject()
        self.assertEqual(approve_action['context']['default_decision'], 'approve')
        self.assertEqual(reject_action['context']['default_decision'], 'reject')
        self.assertEqual(approve_action['res_model'], 'prv.voucher.decision')

    def test_reset_bills_releases_documents_and_preserves_audit(self):
        bill = self._bill()
        voucher = self._voucher(bill)
        voucher.action_submit()
        voucher.action_reset_bills()
        self.assertEqual(voucher.state, 'cancelled')
        self.assertFalse(bill.prv_voucher_id)
        self.assertTrue(voucher.bill_ids)
        self.assertTrue(voucher.history_ids.filtered(lambda item: item.action == 'bills reset'))
        bill.button_draft()
        bill.action_post()
        replacement = self._voucher(bill)
        self.assertNotEqual(replacement, voucher)

    def test_duplicate_and_mixed_partner(self):
        bill = self._bill()
        other = self._bill(partner=self.partner_b)
        with self.assertRaises(UserError):
            self._voucher(bill | other)
        voucher = self._voucher(bill)
        with self.assertRaises(UserError):
            self._voucher(bill)
        voucher.action_cancel()
        self.assertNotEqual(self._voucher(bill), voucher)

    def test_mixed_partner_allowed_when_configuration_disables_requirement(self):
        self.config.require_same_partner = False
        self.config.show_pay_button = True
        first = self._bill(25, partner=self.partner_a)
        second = self._bill(25, partner=self.partner_b)
        voucher = self._voucher(first | second)
        self.assertFalse(voucher.partner_id)
        self.assertEqual(voucher.partner_summary, 'Multiple Partners (2)')
        self.assertEqual(set(voucher.bill_ids.mapped('partner_name')),
                         {self.partner_a.display_name, self.partner_b.display_name})
        voucher.action_submit()
        self._decide(voucher, self.approver)
        self.assertEqual(voucher.state, 'approved')
        (first | second)._prv_check_payment()
        self.assertEqual(voucher.action_pay()['res_model'], 'account.payment.register')

    def test_rejection_can_create_replacement(self):
        bill = self._bill()
        voucher = self._voucher(bill)
        voucher.action_submit()
        self._decide(voucher, self.approver, 'reject', 'Missing supporting documents')
        self.assertEqual(voucher.state, 'rejected')
        self.assertNotEqual(self._voucher(bill), voucher)

    def test_active_delegate_and_route_snapshot(self):
        layer = self.config.layer_ids[:1]
        layer.write({'delegate_id': self.delegate.id, 'valid_from': fields.Date.today(),
                     'valid_until': fields.Date.today() + timedelta(days=1)})
        voucher = self._voucher(self._bill(50))
        voucher.action_submit()
        layer.write({'delegate_id': False})
        self._decide(voucher, self.delegate)
        self.assertEqual(voucher.state, 'approved')
        self.assertTrue(voucher.history_ids[-1].delegated)

    def test_expired_delegate_denied(self):
        self.config.layer_ids[:1].write({'delegate_id': self.delegate.id,
            'valid_from': fields.Date.today() - timedelta(days=2),
            'valid_until': fields.Date.today() - timedelta(days=1)})
        voucher = self._voucher(self._bill(50))
        voucher.action_submit()
        with self.assertRaises(AccessError):
            self._decide(voucher, self.delegate)

    def test_no_config_keeps_standard_flow(self):
        self.config.active = False
        self.assertEqual(self._bill().action_register_payment()['res_model'], 'account.payment.register')
        self.assertEqual(self._bill(kind='out_invoice').action_register_payment()['res_model'], 'account.payment.register')

    def test_receive_config_enforces_approval(self):
        self.config.copy({'voucher_type': 'receive'})
        invoice = self._bill(50, kind='out_invoice')
        with self.assertRaises(UserError):
            invoice.action_register_payment()
        voucher = self._voucher(invoice, 'receive')
        voucher.action_submit()
        self._decide(voucher, self.approver)
        invoice._prv_check_payment()

    def test_configured_pay_button_opens_native_wizard(self):
        self.config.show_pay_button = True
        bill = self._bill(50)
        voucher = self._voucher(bill)
        voucher.action_submit()
        self._decide(voucher, self.approver)
        self.assertTrue(voucher.show_pay_button)
        action = voucher.action_pay()
        self.assertEqual(action['res_model'], 'account.payment.register')
        self.assertEqual(action['target'], 'new')

    def test_disabled_pay_button_is_enforced_in_backend(self):
        bill = self._bill(50)
        voucher = self._voucher(bill)
        voucher.action_submit()
        self._decide(voucher, self.approver)
        self.assertFalse(voucher.show_pay_button)
        with self.assertRaises(AccessError):
            voucher.action_pay()

    def test_workflow_fields_and_context_cannot_forge_approval(self):
        voucher = self._voucher(self._bill())
        with self.assertRaises(AccessError):
            voucher.write({'state': 'approved'})
        with self.assertRaises(AccessError):
            voucher.move_ids.write({'prv_voucher_id': False})
        other = self.env['prv.voucher'].with_context(default_state='approved', default_approved_by_id=self.env.uid).create({
            'voucher_type': 'payment', 'move_ids': [Command.set(self._bill().ids)]})
        self.assertEqual(other.state, 'draft')
        self.assertFalse(other.approved_by_id)
        with self.assertRaises(AccessError):
            voucher.bill_ids.write({'amount': 1})

    def test_active_document_is_frozen(self):
        bill = self._bill()
        self._voucher(bill)
        with self.assertRaises(UserError):
            bill.button_draft()
        with self.assertRaises(UserError):
            bill.invoice_line_ids.write({'name': 'Changed'})

    def test_wizard_rechecks_after_config_activation(self):
        self.config.active = False
        bill = self._bill()
        wizard = self.env['account.payment.register'].with_context(active_model='account.move', active_ids=bill.ids).create({})
        self.config.active = True
        with self.assertRaises(UserError):
            wizard.action_create_payments()

    def test_invoice_line_wizard_is_guarded(self):
        bill = self._bill()
        lines = bill.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable')
        with self.assertRaises(UserError):
            lines.action_register_payment()

    def test_partial_reconcile_guard(self):
        bill = self._bill()
        payable = bill.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable')[:1]
        # Approval must reject before the base reconciliation validates the pairing.
        with self.assertRaisesRegex(UserError, 'Payment is blocked'):
            self.env['account.partial.reconcile'].create({
                'debit_move_id': payable.id, 'credit_move_id': payable.id,
                'amount': 1, 'debit_amount_currency': 1, 'credit_amount_currency': 1})

    def test_detail_snapshot_is_flattened(self):
        bills = self._bill(25) | self._bill(50)
        voucher = self._voucher(bills)
        self.assertEqual(voucher.bill_count, 2)
        self.assertEqual(len(voucher.detail_ids), 2)
        self.assertEqual(voucher.amount_total, 75)

    def test_wrong_document_type_and_draft_rejected(self):
        invoice = self._bill(kind='out_invoice')
        with self.assertRaises(UserError):
            self._voucher(invoice)
        invoice.button_draft()
        with self.assertRaises(UserError):
            self._voucher(invoice, 'receive')

from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from .test_voucher import TestVoucher


@tagged('post_install', '-at_install')
class TestSkipApproval(AccountTestInvoicingCommon):
    _bill = TestVoucher._bill
    _voucher = TestVoucher._voucher
    _decide = TestVoucher._decide

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref('payment_receive_voucher.group_voucher_manager')
        cls.accountant = new_test_user(cls.env, login='skip_accountant', groups='account.group_account_invoice',
                                      company_id=cls.env.company.id, company_ids=[Command.set(cls.env.company.ids)])
        cls.payment_type = cls.env['prv.voucher.payment.type'].create({
            'name': 'Skip Test Payment Type', 'company_id': cls.env.company.id})
        cls.config = cls.env['prv.voucher.config'].create({
            'name': 'Skip Test Payment Approval', 'voucher_type': 'payment',
            'company_id': cls.env.company.id, 'show_pay_button': True,
            'layer_ids': [Command.create({'sequence': 1, 'min_amount': 0, 'approver_id': cls.env.uid})],
        })
        cls.receive_config = cls.config.copy({'name': 'Skip Test Receive Approval', 'voucher_type': 'receive'})
        cls.bank = cls.company_data['default_journal_bank']
        # A real outstanding account makes the wizard create/post/reconcile a
        # payment entry instead of only creating an unposted payment record.
        outstanding = cls.env['account.account'].create({
            'name': 'Skip QA Outstanding', 'code': 'SKIP001', 'account_type': 'asset_current',
            'reconcile': True, 'company_ids': [Command.set(cls.env.company.ids)],
        })
        cls.bank.inbound_payment_method_line_ids.payment_account_id = outstanding
        cls.bank.outbound_payment_method_line_ids.payment_account_id = outstanding

    def _wizard(self, move, amount=None, user=None, context=None):
        ctx = {'active_model': 'account.move', 'active_ids': move.ids, **(context or {})}
        values = {'journal_id': self.bank.id, 'payment_date': fields.Date.today()}
        if amount is not None:
            values['amount'] = amount
        return self.env['account.payment.register'].with_user(user or self.env.user).with_context(**ctx).create(values)

    def _approved(self, move, kind='payment'):
        voucher = self._voucher(move, kind)
        voucher.action_submit()
        self._decide(voucher, self.env.user)
        self.assertEqual(voucher.state, 'approved')
        return voucher

    def test_default_false_and_unchecked_keeps_payment_blocked_for_both_types(self):
        for kind in ('in_invoice', 'out_invoice'):
            move = self._bill(kind=kind)
            self.assertFalse(move.skip_approval)
            with self.assertRaisesRegex(UserError, 'requires an approved'):
                move.action_register_payment()

    def test_accounting_user_can_tick_posted_document_and_open_pay(self):
        for kind in ('in_invoice', 'out_invoice'):
            move = self._bill(kind=kind)
            move.with_user(self.accountant).skip_approval = True
            action = move.with_user(self.accountant).action_register_payment()
            self.assertEqual(action['res_model'], 'account.payment.register')
            wizard = self._wizard(move, user=self.accountant)
            self.assertTrue(wizard.prv_allow_partial_payment)
            self.assertFalse(wizard.prv_has_configured_voucher)

    def test_real_direct_payments_for_vendor_bill_and_customer_invoice(self):
        for kind in ('in_invoice', 'out_invoice'):
            move = self._bill(kind=kind)
            move.skip_approval = True
            before = move.invoice_line_ids.read(['name', 'quantity', 'price_unit', 'tax_ids', 'account_id'])
            payments = self._wizard(move)._create_payments()
            self.assertTrue(payments)
            self.assertTrue(payments.move_id.filtered(lambda entry: entry.state == 'posted'))
            self.assertEqual(move.amount_residual, 0)
            self.assertEqual(move.invoice_line_ids.read(['name', 'quantity', 'price_unit', 'tax_ids', 'account_id']), before)
            self.assertFalse(move.prv_voucher_ids)

    def test_active_draft_waiting_and_approved_voucher_do_not_block_direct_pay(self):
        for kind, voucher_kind in [('in_invoice', 'payment'), ('out_invoice', 'receive')]:
            for state in ('draft', 'waiting', 'approved'):
                with self.subTest(kind=kind, voucher_state=state):
                    move = self._bill(kind=kind)
                    voucher = self._voucher(move, voucher_kind)
                    if state in ('waiting', 'approved'):
                        voucher.action_submit()
                    if state == 'approved':
                        self._decide(voucher, self.env.user)
                    snapshot = voucher.bill_ids.read(['amount', 'original_total', 'move_id'])
                    move.with_user(self.accountant).skip_approval = True
                    self.assertEqual(voucher.state, state)
                    self.assertEqual(move.prv_voucher_id, voucher)
                    self._wizard(move)._create_payments()
                    self.assertEqual(move.amount_residual, 0)
                    self.assertEqual(voucher.state, state)
                    self.assertEqual(voucher.bill_ids.read(['amount', 'original_total', 'move_id']), snapshot)
                    self.assertEqual(voucher.bill_ids.current_due, 0)

    def test_flag_does_not_approve_or_modify_existing_voucher_snapshots(self):
        move = self._bill()
        voucher = self._voucher(move)
        voucher.action_submit()
        before = voucher.read(['state', 'approved_by_id', 'approved_at', 'approved_remarks'])
        steps = voucher.step_ids.read(['state', 'approver_id'])
        snapshots = voucher.bill_ids.read(['amount', 'original_total'])
        move.skip_approval = True
        self.assertEqual(voucher.read(list(before[0])), before)
        self.assertEqual(voucher.step_ids.read(['state', 'approver_id']), steps)
        self.assertEqual(voucher.bill_ids.read(['amount', 'original_total']), snapshots)
        self.assertFalse(move.prv_voucher_approved)

    def test_unchecking_reinstates_approval_guard_in_already_open_wizard(self):
        move = self._bill()
        move.skip_approval = True
        wizard = self._wizard(move)
        move.skip_approval = False
        with self.assertRaisesRegex(UserError, 'requires an approved'):
            wizard._create_payments()
        self.assertEqual(move.amount_residual, 250)

    def test_unflagged_approved_document_still_requires_voucher_pay_route(self):
        move = self._bill()
        voucher = self._approved(move)
        with self.assertRaisesRegex(UserError, 'Pay is blocked from'):
            self._wizard(move)
        payments = self._wizard(move, context={'prv_voucher_payment_id': voucher.id})._create_payments()
        self.assertTrue(payments)
        self.assertEqual(move.amount_residual, 0)
        self.assertFalse(move.skip_approval)

    def test_unflagged_partial_policy_remains_enforced_and_opt_in_still_works(self):
        move = self._bill()
        voucher = self._approved(move)
        ctx = {'prv_voucher_payment_id': voucher.id}
        with self.assertRaisesRegex(UserError, 'does not allow editing'), self.env.cr.savepoint():
            self._wizard(move, amount=100, context=ctx)
        self.config.allow_edit_amount_for_partial_payment = True
        wizard = self._wizard(move, amount=100, context=ctx)
        self.assertTrue(wizard.prv_has_configured_voucher)
        wizard._create_payments()
        self.assertEqual(move.amount_residual, 150)
        self.assertEqual(voucher.bill_ids.current_due, 150)
        self.assertFalse(move.skip_approval)

    def test_partial_pay_direct_ignores_old_voucher_partial_amount_restriction(self):
        move = self._bill()
        voucher = self._approved(move)
        self.assertFalse(voucher.config_id.allow_edit_amount_for_partial_payment)
        move.skip_approval = True
        wizard = self._wizard(move, amount=100)
        self.assertTrue(wizard.prv_allow_partial_payment)
        wizard._create_payments()
        self.assertEqual(move.amount_residual, 150)
        self._wizard(move, amount=150)._create_payments()
        self.assertEqual(move.amount_residual, 0)
        with self.assertRaisesRegex(UserError, 'no outstanding documents'):
            voucher.action_pay()

    def test_stale_second_wizard_cannot_overpay_after_direct_partial_payment(self):
        move = self._bill()
        voucher = self._approved(move)
        move.skip_approval = True
        stale = self._wizard(move)
        self._wizard(move, amount=100)._create_payments()
        with self.assertRaisesRegex(UserError, 'current outstanding balance'):
            stale._create_payments()
        self.assertEqual(move.amount_residual, 150)
        self.assertEqual(voucher.state, 'approved')

    def test_flag_is_not_copied_to_new_invoice_or_credit_note(self):
        move = self._bill()
        move.skip_approval = True
        copied = move.copy()
        self.assertFalse(copied.skip_approval)
        reversal = move._reverse_moves(cancel=False)
        self.assertFalse(reversal.skip_approval)
        self.assertEqual(reversal.move_type, 'in_refund')

    def test_nonaccounting_user_cannot_set_flag_even_through_context(self):
        user = new_test_user(self.env, login='skip_voucher_only', groups='payment_receive_voucher.group_voucher_user')
        move = self._bill()
        with self.assertRaises(AccessError):
            move.with_user(user).write({'skip_approval': True})
        with self.assertRaises(AccessError):
            self.env['account.move'].with_user(user).with_context(default_skip_approval=True).create({})
        self.assertFalse(move.skip_approval)

    def test_direct_create_and_context_default_support_valid_invoice(self):
        for values, ctx in [({'skip_approval': True}, {}), ({}, {'default_skip_approval': True})]:
            move = self.env['account.move'].with_context(**ctx).create({
                'move_type': 'in_invoice', 'partner_id': self.partner_a.id,
                'invoice_date': fields.Date.today(), **values,
                'invoice_line_ids': [Command.create({'name': 'Direct Skip bill', 'price_unit': 100,
                                                   'account_id': self.company_data['default_account_expense'].id,
                                                   'tax_ids': [Command.clear()]})],
            })
            self.assertTrue(move.skip_approval)
            move.action_post()
            self.assertEqual(move.action_register_payment()['res_model'], 'account.payment.register')

    def test_empty_flag_on_journal_entry_is_harmless_but_true_is_rejected(self):
        journal = self.company_data['default_journal_misc']
        move = self.env['account.move'].create({'move_type': 'entry', 'journal_id': journal.id,
                                               'skip_approval': False})
        move.write({'skip_approval': False})
        with self.assertRaisesRegex(ValidationError, 'only available on Customer Invoices'), self.env.cr.savepoint():
            move.write({'skip_approval': True})
        self.assertFalse(move.skip_approval)

    def test_existing_active_voucher_source_amounts_remain_frozen(self):
        move = self._bill()
        self._voucher(move)
        move.skip_approval = True
        with self.assertRaisesRegex(UserError, 'Cancel the active voucher'):
            move.invoice_line_ids.write({'price_unit': 100})
        self.assertEqual(move.amount_total, 250)

    def test_new_voucher_creation_is_rejected_for_flagged_documents(self):
        for kind, voucher_kind in [('in_invoice', 'payment'), ('out_invoice', 'receive')]:
            move = self._bill(kind=kind)
            move.skip_approval = True
            with self.assertRaisesRegex(UserError, 'Skip Approval enabled'):
                self._voucher(move, voucher_kind)
            action = move.action_create_payment_voucher if kind == 'in_invoice' else move.action_create_receive_voucher
            with self.assertRaisesRegex(UserError, 'Skip Approval enabled'):
                action()
            self.assertFalse(move.prv_voucher_ids)

    def test_list_voucher_wizard_rechecks_flag_changed_after_opening(self):
        move = self._bill()
        wizard = self.env['prv.voucher.create'].create({'move_ids': [Command.set(move.ids)]})
        move.skip_approval = True
        with self.assertRaisesRegex(UserError, 'Skip Approval enabled'):
            wizard.action_confirm()

    def test_mixed_payment_batch_does_not_skip_other_document_approval(self):
        allowed, required = self._bill(), self._bill()
        allowed.skip_approval = True
        with self.assertRaisesRegex(UserError, 'requires an approved'):
            self._wizard(allowed | required)
        self.assertEqual(required.amount_residual, 250)

    def test_invoice_line_payment_entry_point_honors_flag(self):
        move = self._bill()
        move.skip_approval = True
        lines = move.line_ids.filtered(lambda line: line.account_id.account_type == 'liability_payable')
        self.assertEqual(lines.action_register_payment()['res_model'], 'account.payment.register')
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move.line', active_ids=lines.ids).create({'journal_id': self.bank.id})
        wizard._create_payments()
        self.assertEqual(move.amount_residual, 0)

    def test_checklist_is_tracked_in_native_chatter(self):
        move = self._bill()
        self.env.flush_all()
        # Model creation in this test transaction discards tracking until its
        # first precommit finalize, unlike an existing bill from a prior request.
        move._track_finalize()
        tracked_move = move.with_user(self.accountant).with_context(tracking_disable=False, mail_notrack=False)
        tracked_move.skip_approval = True
        self.env.flush_all()
        tracked_move._track_finalize()
        move.invalidate_recordset(['message_ids'])
        tracked = move.message_ids.tracking_value_ids.filtered(lambda value: value.field_id.name == 'skip_approval')
        self.assertTrue(tracked)
        self.assertTrue(move.message_ids.filtered(lambda message: message.author_id == self.accountant.partner_id))

    def test_accounting_user_can_complete_native_direct_payment(self):
        move = self._bill()
        move.with_user(self.accountant).skip_approval = True
        payments = self._wizard(move, user=self.accountant)._create_payments()
        self.assertTrue(payments)
        self.assertEqual(move.amount_residual, 0)
        self.assertEqual(payments.create_uid, self.accountant)

    def test_skip_preserves_native_draft_payment_behavior(self):
        source = self._bill()
        skipped = source.copy({'skip_approval': True})
        native = source.copy()
        # Odoo 19 supports registering payments on drafts. Compare against the
        # unchanged native route rather than adding a new posting restriction.
        self.config.active = False
        native_payments = self._wizard(native)._create_payments()
        self.config.active = True
        skipped_payments = self._wizard(skipped)._create_payments()
        self.assertEqual(skipped.state, native.state)
        self.assertEqual(skipped.amount_residual, native.amount_residual)
        self.assertEqual(skipped_payments.mapped('state'), native_payments.mapped('state'))

    def test_native_views_hide_voucher_buttons_when_flagged(self):
        view = self.env.ref('payment_receive_voucher.move_form_voucher')
        arch = etree.fromstring(self.env['account.move'].get_view(view_id=view.id, view_type='form')['arch'])
        self.assertTrue(arch.xpath("//group[@id='header_right_group']//field[@name='skip_approval']"))
        for name in ('action_create_payment_voucher', 'action_create_receive_voucher'):
            buttons = arch.xpath("//header/button[@name='%s']" % name)
            self.assertTrue(buttons)
            self.assertTrue(all('skip_approval' in button.get('invisible', '') for button in buttons))

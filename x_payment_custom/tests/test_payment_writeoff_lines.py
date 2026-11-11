from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPaymentWriteoffLines(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acc_a = cls.company_data['default_account_expense']
        cls.acc_b = cls.copy_account(cls.company_data['default_account_expense'])
        cls.acc_c = cls.company_data['default_account_revenue']

    def _register(self, move, amount):
        return self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=move.ids,
        ).create({
            'amount': amount,
            'payment_date': move.invoice_date,
            'payment_difference_handling': 'reconcile',
        })

    def _check(self, move_type, amount_sign):
        move = self.init_invoice(move_type, amounts=[1000.0], post=True)
        wizard = self._register(move, 600.0)
        self.assertEqual(wizard.payment_difference, 400.0)
        wizard.write({'x_writeoff_line_ids': [
            Command.create({'account_id': self.acc_a.id, 'name': 'WO A1', 'amount': 250.0}),
            Command.create({'account_id': self.acc_b.id, 'name': 'WO A2', 'amount': 100.0}),
            Command.create({'account_id': self.acc_c.id, 'name': 'WO A3', 'amount': 50.0}),
        ]})
        self.assertEqual(wizard.x_writeoff_remaining, 0.0)
        payment = wizard._create_payments()

        wo_lines = payment.move_id.line_ids.filtered(lambda l: l.name and l.name.startswith('WO '))
        self.assertRecordValues(wo_lines.sorted('name'), [
            {'name': 'WO A1', 'account_id': self.acc_a.id, 'balance': amount_sign * 250.0},
            {'name': 'WO A2', 'account_id': self.acc_b.id, 'balance': amount_sign * 100.0},
            {'name': 'WO A3', 'account_id': self.acc_c.id, 'balance': amount_sign * 50.0},
        ])
        self.assertIn(move.payment_state, ('paid', 'in_payment'))

    def test_customer_invoice_multi_writeoff(self):
        # Receiving money: write-off posted on the debit side.
        self._check('out_invoice', 1)

    def test_vendor_bill_multi_writeoff(self):
        # Sending money: write-off posted on the credit side.
        self._check('in_invoice', -1)

    def test_total_must_match_difference(self):
        move = self.init_invoice('out_invoice', amounts=[1000.0], post=True)
        wizard = self._register(move, 600.0)
        wizard.write({'x_writeoff_line_ids': [
            Command.create({'account_id': self.acc_a.id, 'name': 'WO A1', 'amount': 300.0}),
        ]})
        self.assertEqual(wizard.x_writeoff_remaining, 100.0)
        with self.assertRaises(UserError):
            wizard._create_payments()

    def test_no_line_raises(self):
        move = self.init_invoice('out_invoice', amounts=[1000.0], post=True)
        wizard = self._register(move, 600.0)
        with self.assertRaises(UserError):
            wizard._create_payments()

    def test_keep_open_unchanged(self):
        move = self.init_invoice('out_invoice', amounts=[1000.0], post=True)
        wizard = self._register(move, 600.0)
        wizard.payment_difference_handling = 'open'
        wizard._create_payments()
        self.assertEqual(move.payment_state, 'partial')

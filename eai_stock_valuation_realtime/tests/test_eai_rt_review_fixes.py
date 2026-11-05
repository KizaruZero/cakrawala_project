"""Temuan review tim (4 Nov 2026): akses laporan lintas company, credit note multi-baris yang
menutup klaim melebihi qty retur, dan qty laporan interim setelah koreksi harga."""
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_eai_rt_valuation import TestEaiRtValuationBase


@tagged('post_install', '-at_install', 'eai_rt')
class TestEaiRtReviewFixes(TestEaiRtValuationBase):

    def _report(self, role, env=None):
        self.env.flush_all()
        Report = (env or self.env)['eai.rt.balance.report']
        Report.invalidate_model()
        return Report.search([('role', '=', role), ('product_id', '=', self.lm10.id)])

    def _refund_lines(self, bill, quantities):
        """Credit note dari bill dengan beberapa baris untuk PO line yang sama."""
        reversal = self.env['account.move.reversal'].with_context(
            active_ids=bill.ids, active_model='account.move').create({'journal_id': bill.journal_id.id})
        credit_note = self.env['account.move'].browse(reversal.refund_moves()['res_id'])
        line = credit_note.invoice_line_ids.filtered('product_id')
        line.quantity = quantities[0]
        for qty in quantities[1:]:
            credit_note.write({'invoice_line_ids': [Command.create({
                'product_id': line.product_id.id,
                'quantity': qty,
                'price_unit': line.price_unit,
                'tax_ids': [Command.clear()],
                'purchase_line_id': line.purchase_line_id.id,
            })]})
        return credit_note

    # Poin 3 -------------------------------------------------------------
    def test_report_restricted_to_allowed_companies(self):
        po = self._po(2, 100)
        self._receive(po)
        self.assertTrue(self._report('input'), "Saldo Stock Input company A tampil untuk user A")
        company_b = self.env['res.company'].create({'name': 'EAI Company B'})
        user_b = self.env['res.users'].create({
            'name': 'User B', 'login': 'eai_user_b',
            'company_id': company_b.id, 'company_ids': [Command.set(company_b.ids)],
            'group_ids': [Command.set([self.env.ref('base.group_user').id,
                                       self.env.ref('account.group_account_readonly').id])],
        })
        env_b = self.env(user=user_b, context=dict(self.env.context, allowed_company_ids=company_b.ids))
        self.assertFalse(self._report('input', env_b), "User company B tidak boleh melihat saldo company A")
        self.assertFalse(env_b['eai.rt.balance.report'].search([('company_id', '=', self.company.id)]))

    # Poin 4 -------------------------------------------------------------
    def test_credit_note_lines_cannot_exceed_returned_qty(self):
        po = self._po(2, 1000)
        bill = self._bill(po)
        receipt = self._receive(po)
        self._return(receipt, 1)
        credit_note = self._refund_lines(bill, [0.6, 0.6])
        with self.assertRaises(UserError):
            credit_note.action_post()
        self.assertAlmostEqual(self._balance(self.acc_claim), 1000)

    def test_credit_note_lines_within_returned_qty(self):
        po = self._po(2, 1000)
        bill = self._bill(po)
        receipt = self._receive(po)
        self._return(receipt, 1)
        credit_note = self._refund_lines(bill, [0.5, 0.5])
        credit_note.action_post()
        self.assertTrue(all(credit_note.invoice_line_ids.filtered('product_id').mapped('eai_rt_is_claim')))
        self.assertAlmostEqual(self._balance(self.acc_claim), 0)

    # Poin 5 -------------------------------------------------------------
    def test_report_qty_after_price_correction(self):
        po = self._po(6, 100)
        receipt = self._receive(po)
        self._bill(po, qty=2, price=110)
        self.assertTrue(receipt.move_ids.eai_rt_account_move_ids.filtered(
            lambda m: m.id != receipt.move_ids.account_move_id.id), "Ada jurnal koreksi harga")
        row = self._report('input')
        self.assertEqual(len(row), 1)
        self.assertAlmostEqual(row.quantity, -4, msg="4 unit diterima belum ditagih")

    def test_report_claim_qty_after_credit_note_difference(self):
        po = self._po(2, 1000)
        bill = self._bill(po)
        receipt = self._receive(po)
        self._return(receipt, 2)
        self._refund(bill, quantity=1, price=950)
        row = self._report('claim')
        self.assertEqual(len(row), 1)
        self.assertAlmostEqual(row.balance, 1000)
        self.assertAlmostEqual(row.quantity, 1, msg="1 unit retur belum di-credit-note")

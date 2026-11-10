"""Transaksi valuta asing (PO/SO/bill/invoice/credit note EUR, mata uang perusahaan lain).

Invarian: GL persediaan = nilai valuasi Odoo; Stock Input, Stock Output, Piutang Klaim nol
setelah dokumen lengkap; semua jurnal valuasi dalam mata uang perusahaan.
"""
from dateutil.relativedelta import relativedelta
from odoo import Command, fields
from odoo.tests import tagged

from .test_eai_rt_valuation import TestEaiRtValuationBase as Base

D0 = fields.Date.today()                  # GR/DO hari ini: kurs 17.000
D1 = D0 - relativedelta(days=3)           # kurs 17.500
D2 = D0 - relativedelta(days=6)           # kurs 18.000


@tagged('post_install', '-at_install', 'eai_rt')
class TestEaiRtForeignCurrency(Base):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 1 USD = 17.000 (D0), 17.500 (D1), 18.000 (D2) mata uang perusahaan
        rates = {0: 17000.0, 1: 17000.0, 2: 17500.0, 3: 17500.0, 4: 17500.0,
                 5: 18000.0, 6: 18000.0, 7: 18000.0, 8: 18000.0}
        cls.fx = cls.setup_other_currency('EUR', rates=[
            (fields.Date.to_string(D0 - relativedelta(days=d)), 1 / r) for d, r in rates.items()])
        assert cls.fx != cls.company.currency_id, cls.company.currency_id.name
        cls.pricelist_fx = cls.env['product.pricelist'].create({
            'name': 'FX', 'currency_id': cls.fx.id, 'company_id': cls.company.id})

    def _po_fx(self, qty, price):
        po = self.env['purchase.order'].create({
            'partner_id': self.antam.id, 'company_id': self.company.id, 'currency_id': self.fx.id,
            'order_line': [Command.create({'product_id': self.lm10.id, 'product_qty': qty,
                                           'price_unit': price, 'tax_ids': [Command.clear()]})],
        })
        po.button_confirm()
        return po

    def _bill_fx(self, po, date, qty=None):
        po.action_create_invoice()
        bill = po.invoice_ids.filtered(lambda m: m.state == 'draft')[-1:]
        bill.invoice_date = date
        bill.date = date
        if qty is not None:
            bill.invoice_line_ids.filtered('product_id').quantity = qty
        bill.action_post()
        return bill

    def _refund_fx(self, move, date, quantity=None):
        reversal = self.env['account.move.reversal'].with_context(
            active_ids=move.ids, active_model='account.move').create({
                'journal_id': move.journal_id.id, 'date': date})
        cn = self.env['account.move'].browse(reversal.refund_moves()['res_id'])
        cn.invoice_date = date
        cn.date = date
        if quantity is not None:
            cn.invoice_line_ids.filtered('product_id').quantity = quantity
        cn.action_post()
        return cn

    def _so_fx(self, qty, price):
        so = self.env['sale.order'].create({
            'partner_id': self.customer.id, 'company_id': self.company.id,
            'pricelist_id': self.pricelist_fx.id,
            'order_line': [Command.create({'product_id': self.lm10.id, 'product_uom_qty': qty,
                                           'price_unit': price, 'tax_ids': [Command.clear()]})],
        })
        so.action_confirm()
        self.assertEqual(so.currency_id, self.fx)
        return so

    def _invoice_fx(self, so, date):
        inv = so._create_invoices()
        inv.invoice_date = date
        inv.date = date
        inv.action_post()
        return inv

    def _check(self, label, input0=True, output0=True, claim0=True):
        p = self.lm10
        p.invalidate_recordset()
        stock = self._balance(self.acc_stock, p)
        vals = dict(stock_gl=stock, total_value=p.total_value, input=self._balance(self.acc_input),
                    output=self._balance(self.acc_output), claim=self._balance(self.acc_claim),
                    price_diff=self._balance(self.acc_price_diff))
        self.assertAlmostEqual(stock, p.total_value, places=2, msg=f"{label}: GL persediaan != valuasi")
        if input0:
            self.assertAlmostEqual(vals['input'], 0, places=2, msg=f"{label}: Stock Input")
        if output0:
            self.assertAlmostEqual(vals['output'], 0, places=2, msg=f"{label}: Stock Output")
        if claim0:
            self.assertAlmostEqual(vals['claim'], 0, places=2, msg=f"{label}: Piutang Klaim")
        # semua jurnal addon seimbang dan dalam mata uang perusahaan
        entries = self.env['account.move'].search([('eai_rt_stock_move_id', '!=', False)])
        for line in entries.line_ids:
            self.assertEqual(line.currency_id, self.company.currency_id)
        return vals

    def _input_bal(self, bill):
        return sum(bill.line_ids.filtered(lambda l: l.account_id == self.acc_input).mapped('balance'))

    def test_fx1_receipt_then_bill_other_rate(self):
        po = self._po_fx(2, 1000)
        receipt = self._receive(po)
        gr_value = self._check('fx1 setelah GR', input0=False)['stock_gl']
        bill = self._bill_fx(po, D1)
        ap = bill.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable')
        self.assertAlmostEqual(ap.amount_currency, -2000)
        self.assertNotAlmostEqual(gr_value, self._input_bal(bill), msg="kurs GR dan bill harus beda")
        v = self._check('fx1 setelah bill')
        self.assertAlmostEqual(v['stock_gl'], self._input_bal(bill))
        self.assertEqual(len(receipt.move_ids.eai_rt_account_move_ids), 2)

    def test_fx2_bill_first_then_receipt(self):
        po = self._po_fx(2, 1000)
        bill = self._bill_fx(po, D1)
        self._receive(po)
        v = self._check('fx2 bill dulu')
        self.assertAlmostEqual(v['stock_gl'], self._input_bal(bill))

    def test_fx3_vendor_return_credit_note_other_rate(self):
        po = self._po_fx(2, 1000)
        bill = self._bill_fx(po, D1)
        receipt = self._receive(po)
        self._return(receipt, 1)
        v = self._check('fx3 setelah retur', claim0=False)
        claim = self._input_bal(bill) / 2
        self.assertAlmostEqual(v['claim'], claim)
        cn = self._refund_fx(bill, D2, quantity=1)
        cn_value = -sum(cn.invoice_line_ids.filtered('product_id').mapped('balance'))
        self.assertNotAlmostEqual(cn_value, claim, msg="kurs credit note harus beda")
        v = self._check('fx3 setelah credit note')
        self.assertAlmostEqual(v['price_diff'], claim - cn_value)

    def test_fx4_sale_in_fx(self):
        po = self._po_fx(4, 1000)
        bill = self._bill_fx(po, D0)
        self._receive(po)
        so = self._so_fx(2, 1200)
        self._deliver(so)
        do_value = self._check('fx4 setelah DO', output0=False)['output']
        self.assertAlmostEqual(do_value, self._input_bal(bill) / 2)
        inv = self._invoice_fx(so, D1)
        rev = inv.invoice_line_ids.filtered('product_id')
        self.assertEqual(rev.currency_id, self.fx)
        self.assertAlmostEqual(rev.amount_currency, -2400)
        cogs = inv.line_ids.filtered(lambda l: l.display_type == 'cogs' and l.balance > 0)
        self.assertAlmostEqual(sum(cogs.mapped('balance')), do_value)
        self._check('fx4 setelah invoice')

    def test_fx5_sale_return_and_customer_credit_note_fx(self):
        po = self._po_fx(4, 1000)
        self._bill_fx(po, D0)
        self._receive(po)
        so = self._so_fx(2, 1200)
        delivery = self._deliver(so)
        inv = self._invoice_fx(so, D1)
        self._return(delivery, 1)
        self._check('fx5 setelah retur jual', output0=False)
        self._refund_fx(inv, D2, quantity=1)
        self._check('fx5 setelah CN customer')

    def test_fx6_bill_after_delivery_other_rate(self):
        po = self._po_fx(2, 1000)
        self._receive(po)
        so = self._so_fx(1, 1200)
        self._deliver(so)
        self._invoice_fx(so, D0)
        self._bill_fx(po, D1)
        self._check('fx6 bill telat setelah terjual', output0=False)

    def test_fx7_partial_credit_note_and_reset_draft(self):
        po = self._po_fx(3, 1000)
        bill = self._bill_fx(po, D1)
        receipt = self._receive(po)
        self._return(receipt, 2)
        cn = self._refund_fx(bill, D2, quantity=2)
        self._check('fx7 CN 2 unit')
        cn.button_draft()
        cn.action_post()
        self._check('fx7 CN reset+post ulang')

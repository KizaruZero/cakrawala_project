"""Skenario uji addon valuasi real-time (lihat spec bagian 6).

Angka mengikuti tes manual 20 Okt 2026 (LM 10 Gram): bill 1 @2.400.000, bill 2 @2.350.000,
rata-rata 2.366.666,67, retur 1 unit dari PO kedua.
"""
from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from odoo.addons.stock_account.tests.common import TestStockValuationCommon


class TestEaiRtValuationBase(TestStockValuationCommon):

    _test_user_groups = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']

        def acc(code, name, account_type):
            return Account.create({
                'code': code, 'name': name, 'account_type': account_type,
                'company_ids': [Command.link(cls.company.id)],
            })

        cls.acc_input = acc('113181', 'Persediaan dalam Perjalanan', 'asset_current')
        cls.acc_output = acc('113182', 'Barang Terkirim Belum Ditagih', 'asset_current')
        cls.acc_claim = acc('113183', 'Piutang Klaim Retur Pembelian', 'asset_current')
        cls.acc_price_diff = acc('661131', 'Selisih Nilai Retur Persediaan', 'expense')
        cls.acc_inv_diff = acc('661132', 'Selisih Persediaan', 'expense')
        cls.acc_scrap = acc('661133', 'Beban Persediaan Rusak', 'expense')
        cls.acc_stock = cls.account_stock_valuation

        cls.categ_lm = cls.env['product.category'].create({
            'name': 'LM Emas',
            'property_valuation': 'real_time',
            'property_cost_method': 'average',
        })
        cls.categ_lm.write({
            'eai_rt_enabled': True,
            'eai_rt_stock_input_account_id': cls.acc_input.id,
            'eai_rt_stock_output_account_id': cls.acc_output.id,
            'eai_rt_claim_account_id': cls.acc_claim.id,
            'eai_rt_price_diff_account_id': cls.acc_price_diff.id,
            'eai_rt_inventory_diff_account_id': cls.acc_inv_diff.id,
            'eai_rt_scrap_account_id': cls.acc_scrap.id,
        })
        cls.lm10 = cls.env['product.product'].create({
            'name': 'LM 10 Gram',
            'is_storable': True,
            'categ_id': cls.categ_lm.id,
            'uom_id': cls.uom.id,
            'standard_price': 0.0,
            'list_price': 2500000.0,
            'invoice_policy': 'delivery',
            'purchase_method': 'purchase',
            'supplier_taxes_id': [Command.clear()],
            'taxes_id': [Command.clear()],
        })
        cls.antam = cls.env['res.partner'].create({'name': 'ANTAM', 'company_id': cls.company.id})
        cls.customer = cls.env['res.partner'].create({'name': 'Marketplace', 'company_id': cls.company.id})

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    def _po(self, qty, price, product=None):
        po = self.env['purchase.order'].create({
            'partner_id': self.antam.id,
            'company_id': self.company.id,
            'order_line': [Command.create({
                'product_id': (product or self.lm10).id,
                'product_qty': qty,
                'price_unit': price,
                'tax_ids': [Command.clear()],
            })],
        })
        po.button_confirm()
        return po

    def _bill(self, po, qty=None, price=None):
        po.action_create_invoice()
        bill = po.invoice_ids.filtered(lambda m: m.state == 'draft')[-1:]
        bill.invoice_date = fields.Date.today()
        line = bill.invoice_line_ids.filtered(lambda l: l.product_id)
        if qty is not None:
            line.quantity = qty
        if price is not None:
            line.price_unit = price
        bill.action_post()
        return bill

    def _receive(self, po, qty=None):
        picking = po.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))[:1]
        move = picking.move_ids
        move.quantity = qty if qty is not None else move.product_uom_qty
        move.picked = True
        res = picking.button_validate()
        if isinstance(res, dict) and res.get('res_model'):
            # Wizard backorder: buat backorder untuk sisa qty.
            Form.from_action(self.env, res).save().process()
        return picking

    def _return(self, picking, qty):
        wizard = self.env['stock.return.picking'].with_context(
            active_id=picking.id, active_ids=picking.ids, active_model='stock.picking').create({})
        wizard.product_return_moves.quantity = qty
        return_pick = wizard._create_return()
        return_pick.move_ids.product_uom_qty = qty
        return_pick.move_ids.quantity = qty
        return_pick.move_ids.picked = True
        return_pick.button_validate()
        return return_pick

    def _refund(self, move_to_refund, quantity=None, price=None):
        reversal = self.env['account.move.reversal'].with_context(
            active_ids=move_to_refund.ids, active_model='account.move').create({
                'journal_id': move_to_refund.journal_id.id,
            })
        credit_note = self.env['account.move'].browse(reversal.refund_moves()['res_id'])
        line = credit_note.invoice_line_ids.filtered(lambda l: l.product_id)
        if quantity is not None:
            line.quantity = quantity
        if price is not None:
            line.price_unit = price
        credit_note.action_post()
        return credit_note

    def _so(self, qty, price=2500000.0, product=None):
        so = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'order_line': [Command.create({
                'product_id': (product or self.lm10).id,
                'product_uom_qty': qty,
                'price_unit': price,
                'tax_ids': [Command.clear()],
            })],
        })
        so.action_confirm()
        return so

    def _deliver(self, so, qty=None):
        picking = so.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))[:1]
        move = picking.move_ids
        move.quantity = qty if qty is not None else move.product_uom_qty
        move.picked = True
        picking.button_validate()
        return picking

    def _balance(self, account, product=None):
        domain = [('account_id', '=', account.id), ('parent_state', '=', 'posted'),
                  ('company_id', '=', self.company.id)]
        if product:
            domain.append(('product_id', '=', product.id))
        return sum(self.env['account.move.line'].search(domain).mapped('balance'))

    def _rt_lines(self, stock_moves):
        return stock_moves.eai_rt_account_move_ids.line_ids

    def _assert_line(self, lines, account, balance):
        found = lines.filtered(lambda l: l.account_id == account)
        self.assertTrue(found, f"Tidak ada baris di akun {account.display_name}")
        self.assertAlmostEqual(sum(found.mapped('balance')), balance, places=2,
                               msg=f"Saldo {account.display_name}")


@tagged('post_install', '-at_install', 'eai_rt')
class TestEaiRtValuation(TestEaiRtValuationBase):

    # ------------------------------------------------------------------
    # U-01, U-02, U-06, U-07, U-10, U-18, U-20: alur lengkap angka spec 4.4
    # ------------------------------------------------------------------
    def test_01_full_flow_spec_numbers(self):
        # Bill sebelum GR -> Dr Stock Input / Cr AP
        po1 = self._po(1, 2400000)
        bill1 = self._bill(po1)
        bill_line = bill1.invoice_line_ids.filtered('product_id')
        self.assertEqual(bill_line.account_id, self.acc_input)
        self.assertAlmostEqual(self._balance(self.acc_input), 2400000)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), 0)

        # GR (Diterima) -> Dr Stock / Cr Stock Input
        receipt1 = self._receive(po1)
        lines = self._rt_lines(receipt1.move_ids)
        self._assert_line(lines, self.acc_stock, 2400000)
        self._assert_line(lines, self.acc_input, -2400000)
        self.assertEqual(lines.move_id.state, 'posted')
        self.assertEqual(lines.move_id.partner_id, self.antam)
        self.assertAlmostEqual(self._balance(self.acc_input), 0)

        po2 = self._po(2, 2350000)
        self._bill(po2)
        receipt2 = self._receive(po2)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), 7100000)
        self.assertAlmostEqual(self.lm10.standard_price, 2366666.67, places=2)

        # Retur 1 unit dari PO kedua: Cr Stock @rata-rata, Dr Klaim @harga bill, Dr Selisih
        return_pick = self._return(receipt2, 1)
        lines = self._rt_lines(return_pick.move_ids)
        self._assert_line(lines, self.acc_stock, -2366666.67)
        self._assert_line(lines, self.acc_claim, 2350000)
        self._assert_line(lines, self.acc_price_diff, 16666.67)
        self.assertAlmostEqual(return_pick.move_ids.eai_rt_claim_value, 2350000)

        # Credit note ANTAM 1 @2.350.000 menutup klaim, nilai receipt tidak berubah
        bill2 = po2.invoice_ids.filtered(lambda m: m.move_type == 'in_invoice')
        receipt2_value = receipt2.move_ids.value
        credit_note = self._refund(bill2, quantity=1)
        cn_line = credit_note.invoice_line_ids.filtered('product_id')
        self.assertEqual(cn_line.account_id, self.acc_claim)
        self.assertTrue(cn_line.eai_rt_is_claim)
        self.assertAlmostEqual(self._balance(self.acc_claim), 0)
        self.assertAlmostEqual(receipt2.move_ids.value, receipt2_value)

        # Jual 1 unit: DO -> Dr Output / Cr Stock; invoice final -> Dr HPP / Cr Output
        so = self._so(1)
        delivery = self._deliver(so)
        lines = self._rt_lines(delivery.move_ids)
        self._assert_line(lines, self.acc_output, 2366666.67)
        self._assert_line(lines, self.acc_stock, -2366666.67)
        invoice = so._create_invoices()
        invoice.action_post()
        cogs = invoice.line_ids.filtered(lambda l: l.display_type == 'cogs')
        self._assert_line(cogs, self.acc_output, -2366666.67)
        self._assert_line(cogs, self.account_expense, 2366666.67)
        self.assertFalse(cogs.filtered(lambda l: l.account_id == self.acc_stock))
        self.assertAlmostEqual(self._balance(self.acc_output), 0)

        # GL persediaan = nilai valuasi produk (beda pembulatan maksimal 0,01)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), self.lm10.total_value, delta=0.011)
        self.assertAlmostEqual(self._balance(self.acc_input), 0)

        # Stock Closing: kategori bertanda tidak menghasilkan Stock Variation
        closing_vals = self.company._action_close_stock_valuation()
        stock_closing = [v for v in closing_vals if v['account_id'] == self.acc_stock.id]
        self.assertFalse(stock_closing, "Stock closing tidak boleh mengoreksi kategori bertanda")

        # Jual unit terakhir: sisa pembulatan dibersihkan, GL persediaan produk = 0
        so_last = self._so(1)
        self._deliver(so_last)
        self.assertAlmostEqual(self.lm10.qty_available, 0)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), 0, places=2)
        last_invoice = so_last._create_invoices()
        last_invoice.action_post()

        # Laporan rekonsiliasi: tidak ada saldo interim terbuka
        self.env.flush_all()
        report = self.env['eai.rt.balance.report'].search([('company_id', '=', self.company.id)])
        self.assertFalse(report)

    # ------------------------------------------------------------------
    # U-03 GR parsial dua kali
    # ------------------------------------------------------------------
    def test_02_partial_receipts(self):
        po = self._po(10, 1000)
        self._bill(po)
        self.assertAlmostEqual(self._balance(self.acc_input), 10000)
        first = self._receive(po, 6)
        self.assertAlmostEqual(self._balance(self.acc_input), 4000)
        self._assert_line(self._rt_lines(first.move_ids), self.acc_stock, 6000)
        self.env.flush_all()
        report = self.env['eai.rt.balance.report'].search([
            ('company_id', '=', self.company.id), ('role', '=', 'input')])
        self.assertEqual(report.origin_ref, po.name)
        self.assertAlmostEqual(report.balance, 4000)
        self.assertAlmostEqual(report.quantity, 4)
        self._receive(po, 4)
        self.assertAlmostEqual(self._balance(self.acc_input), 0)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), 10000)

    # ------------------------------------------------------------------
    # U-04 / U-05 GR sebelum bill, harga bill berbeda -> koreksi delta
    # ------------------------------------------------------------------
    def test_03_receipt_before_bill_price_change(self):
        po = self._po(2, 100)
        receipt = self._receive(po)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), 200)
        self.assertAlmostEqual(self._balance(self.acc_input), -200)
        self._bill(po, price=110)
        self.assertAlmostEqual(receipt.move_ids.value, 220)
        self.assertEqual(len(receipt.move_ids.eai_rt_account_move_ids), 2, "Jurnal awal + koreksi delta")
        self.assertAlmostEqual(self._balance(self.acc_input), 0)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), 220)
        self.assertAlmostEqual(self.lm10.total_value, 220)

    # ------------------------------------------------------------------
    # U-08 credit note untuk qty yang belum pernah diterima
    # ------------------------------------------------------------------
    def test_04_refund_not_received(self):
        po = self._po(3, 500)
        bill = self._bill(po)
        self._receive(po, 2)
        credit_note = self._refund(bill, quantity=1)
        line = credit_note.invoice_line_ids.filtered('product_id')
        self.assertEqual(line.account_id, self.acc_input)
        self.assertFalse(line.eai_rt_is_claim)
        self.assertAlmostEqual(self._balance(self.acc_input), 0)

    # ------------------------------------------------------------------
    # T-05: credit note bernilai lain dari klaim -> selisih ke Akun Selisih Harga
    # ------------------------------------------------------------------
    def test_05_refund_price_differs_from_claim(self):
        po = self._po(2, 1000)
        bill = self._bill(po)
        receipt = self._receive(po)
        self._return(receipt, 1)
        self.assertAlmostEqual(self._balance(self.acc_claim), 1000)
        self._refund(bill, quantity=1, price=950)
        self.assertAlmostEqual(self._balance(self.acc_claim), 0)
        self.assertAlmostEqual(self._balance(self.acc_price_diff), 50)

    # ------------------------------------------------------------------
    # U-13 retur jual + credit note customer
    # ------------------------------------------------------------------
    def test_06_sale_return(self):
        po = self._po(2, 1000)
        self._bill(po)
        self._receive(po)
        so = self._so(1, 1500)
        delivery = self._deliver(so)
        invoice = so._create_invoices()
        invoice.action_post()
        return_pick = self._return(delivery, 1)
        lines = self._rt_lines(return_pick.move_ids)
        self._assert_line(lines, self.acc_stock, 1000)
        self._assert_line(lines, self.acc_output, -1000)
        reversal = self.env['account.move.reversal'].with_context(
            active_ids=invoice.ids, active_model='account.move').create({'journal_id': invoice.journal_id.id})
        credit_note = self.env['account.move'].browse(reversal.refund_moves()['res_id'])
        credit_note.action_post()
        self.assertAlmostEqual(self._balance(self.acc_output), 0)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), 2000)

    # ------------------------------------------------------------------
    # U-14 opname lebih dan kurang
    # ------------------------------------------------------------------
    def test_07_inventory_adjustment(self):
        po = self._po(2, 1000)
        self._bill(po)
        self._receive(po)
        quant = self.env['stock.quant'].search([
            ('product_id', '=', self.lm10.id), ('location_id', '=', self.stock_location.id)])
        quant.inventory_quantity = 3
        quant.action_apply_inventory()
        self.assertAlmostEqual(self._balance(self.acc_inv_diff), -1000)
        quant.inventory_quantity = 1
        quant.action_apply_inventory()
        self.assertAlmostEqual(self._balance(self.acc_inv_diff), 1000)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), self.lm10.total_value, places=2)

    # ------------------------------------------------------------------
    # U-19 kategori tidak bertanda = standar Odoo 19
    # ------------------------------------------------------------------
    def test_08_unflagged_category_is_standard(self):
        product = self.product_avco_auto if hasattr(self, 'product_avco_auto') else self.env['product.product'].create({
            'name': 'Busi', 'is_storable': True, 'categ_id': self.category_avco_auto.id})
        po = self._po(1, 100, product=product)
        bill = self._bill(po)
        self.assertEqual(bill.invoice_line_ids.filtered('product_id').account_id, self.acc_stock)
        receipt = self._receive(po)
        self.assertFalse(receipt.move_ids.eai_rt_account_move_ids)

    # ------------------------------------------------------------------
    # Proteksi dan validasi konfigurasi
    # ------------------------------------------------------------------
    def test_09_entries_are_protected(self):
        po = self._po(1, 1000)
        receipt = self._receive(po)
        entry = receipt.move_ids.eai_rt_account_move_ids
        with self.assertRaises(UserError):
            entry.button_draft()
        with self.assertRaises(UserError):
            entry._reverse_moves()

    def test_10_config_constraints(self):
        with self.assertRaises(ValidationError):
            self.env['product.category'].create({
                'name': 'Salah', 'property_valuation': 'periodic',
                'property_cost_method': 'average', 'eai_rt_enabled': True,
            })
        with self.assertRaises(ValidationError):
            self.categ_lm.property_cost_method = 'standard'

    def test_11_missing_account_message(self):
        self.categ_lm.eai_rt_stock_input_account_id = False
        po = self._po(1, 1000)
        with self.assertRaises(UserError):
            self._bill(po)

    # ------------------------------------------------------------------
    # U-11 invoice DP 100% lalu DO + invoice final
    # ------------------------------------------------------------------
    def test_12_down_payment_then_final_invoice(self):
        po = self._po(1, 1000)
        self._bill(po)
        self._receive(po)
        so = self._so(1, 1500)
        wizard = self.env['sale.advance.payment.inv'].with_context(
            active_model='sale.order', active_ids=so.ids, active_id=so.id).create({
                'advance_payment_method': 'percentage', 'amount': 100,
            })
        wizard.create_invoices()
        dp_invoice = so.invoice_ids
        dp_invoice.action_post()
        self.assertFalse(dp_invoice.line_ids.filtered(lambda l: l.display_type == 'cogs'),
                         "Invoice DP tidak membawa HPP")
        self.assertAlmostEqual(self._balance(self.acc_output), 0)
        self._deliver(so)
        self.assertAlmostEqual(self._balance(self.acc_output), 1000)
        final = so._create_invoices(final=True)
        final.action_post()
        self._assert_line(final.line_ids.filtered(lambda l: l.display_type == 'cogs'), self.account_expense, 1000)
        self.assertAlmostEqual(self._balance(self.acc_output), 0)

    # ------------------------------------------------------------------
    # U-12 invoice final setelah rata-rata berubah: HPP tetap = nilai DO
    # ------------------------------------------------------------------
    def test_13_invoice_after_average_changed(self):
        po = self._po(1, 1000)
        self._bill(po)
        self._receive(po)
        so = self._so(1, 1500)
        self._deliver(so)
        po2 = self._po(1, 3000)
        self._bill(po2)
        self._receive(po2)
        self.assertAlmostEqual(self.lm10.standard_price, 3000)
        invoice = so._create_invoices()
        invoice.action_post()
        self._assert_line(invoice.line_ids.filtered(lambda l: l.display_type == 'cogs'), self.account_expense, 1000)
        self.assertAlmostEqual(self._balance(self.acc_output), 0)

    # ------------------------------------------------------------------
    # Invoice sebelum DO (invoicing policy = ordered): Output tetap nol setelah DO
    # ------------------------------------------------------------------
    def test_14_invoice_before_delivery(self):
        self.lm10.invoice_policy = 'order'
        po = self._po(2, 1000)
        self._bill(po)
        self._receive(po)
        so = self._so(1, 1500)
        invoice = so._create_invoices()
        invoice.action_post()
        self._deliver(so)
        self.assertAlmostEqual(self._balance(self.acc_output), 0)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), 1000)

    # ------------------------------------------------------------------
    # Transfer antar gudang/butik: tidak ada jurnal (akun sama)
    # ------------------------------------------------------------------
    def test_15_internal_transfer_no_entry(self):
        po = self._po(2, 1000)
        self._bill(po)
        self._receive(po)
        sub_location = self.env['stock.location'].create({
            'name': 'Etalase', 'location_id': self.stock_location.id, 'usage': 'internal'})
        move = self.env['stock.move'].create({
            'product_id': self.lm10.id, 'product_uom_qty': 1, 'product_uom': self.uom.id,
            'location_id': self.stock_location.id, 'location_dest_id': sub_location.id,
            'company_id': self.company.id,
        })
        move._action_confirm()
        move._action_assign()
        move.quantity = 1
        move.picked = True
        move._action_done()
        self.assertFalse(move.eai_rt_account_move_ids)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), 2000)

    # ------------------------------------------------------------------
    # Cut-over: flag diaktifkan saat sudah ada stok -> transaksi lama tidak dijurnal ulang
    # ------------------------------------------------------------------
    def test_16_enable_flag_with_existing_stock(self):
        categ = self.env['product.category'].create({
            'name': 'Silver (belum aktif)', 'property_valuation': 'real_time', 'property_cost_method': 'average',
        })
        product = self.env['product.product'].create({
            'name': 'Silver 100 Gram', 'is_storable': True, 'categ_id': categ.id,
            'supplier_taxes_id': [Command.clear()], 'taxes_id': [Command.clear()],
        })
        po = self._po(2, 1000, product=product)
        receipt = self._receive(po)
        self.assertFalse(receipt.move_ids.eai_rt_account_move_ids)
        categ.write({
            'eai_rt_enabled': True,
            'eai_rt_stock_input_account_id': self.acc_input.id,
            'eai_rt_stock_output_account_id': self.acc_output.id,
            'eai_rt_price_diff_account_id': self.acc_price_diff.id,
        })
        self.assertAlmostEqual(receipt.move_ids.eai_rt_posted_value, 2000)
        # Bill datang setelah aktivasi dengan harga lain: hanya selisihnya yang dijurnal
        self._bill(po, price=1100)
        entries = receipt.move_ids.eai_rt_account_move_ids
        self.assertEqual(len(entries), 1)
        self._assert_line(entries.line_ids, self.acc_stock, 200)

    # ------------------------------------------------------------------
    # Odoo 19: scrap dikenali dari dokumen scrap
    # ------------------------------------------------------------------
    def test_17_scrap(self):
        po = self._po(2, 1000)
        self._bill(po)
        self._receive(po)
        scrap = self.env['stock.scrap'].create({
            'product_id': self.lm10.id, 'scrap_qty': 1, 'product_uom_id': self.uom.id,
            'location_id': self.stock_location.id, 'company_id': self.company.id,
        })
        scrap.action_validate()
        lines = self._rt_lines(scrap.move_ids)
        self._assert_line(lines, self.acc_stock, -1000)
        self._assert_line(lines, self.acc_scrap, 1000)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), 1000)

    # ------------------------------------------------------------------
    # Odoo 19: baris selisih klaim ikut hilang saat credit note di-reset ke draft
    # ------------------------------------------------------------------
    def test_18_claim_difference_survives_reset_to_draft(self):
        po = self._po(2, 1000)
        bill = self._bill(po)
        receipt = self._receive(po)
        self._return(receipt, 1)
        credit_note = self._refund(bill, quantity=1, price=950)
        self.assertAlmostEqual(self._balance(self.acc_price_diff), 50)
        credit_note.button_draft()
        self.assertFalse(credit_note.line_ids.filtered(lambda l: l.account_id == self.acc_price_diff))
        self.assertAlmostEqual(self._balance(self.acc_claim), 1000)
        credit_note.action_post()
        self.assertAlmostEqual(self._balance(self.acc_claim), 0)
        self.assertAlmostEqual(self._balance(self.acc_price_diff), 50)


    # ------------------------------------------------------------------
    # Odoo 19: bill dengan harga lain datang setelah sebagian barang dikirim
    # ------------------------------------------------------------------
    def test_19_bill_price_change_after_delivery(self):
        po = self._po(2, 1000)
        receipt = self._receive(po)
        so = self._so(1, 1500)
        self._deliver(so)
        self._bill(po, price=1200)
        self.env.flush_all()
        self.lm10.invalidate_recordset()
        # Odoo 19 menilai sisa 1 unit @1.200; porsi unit yang sudah terkirim (200) ke selisih harga.
        self.assertAlmostEqual(self.lm10.total_value, 1200)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), self.lm10.total_value, places=2)
        self.assertAlmostEqual(self._balance(self.acc_price_diff), 200)
        self.assertAlmostEqual(self._balance(self.acc_input), 0)

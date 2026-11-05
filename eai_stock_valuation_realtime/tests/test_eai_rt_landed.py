from odoo import Command
from odoo.tests import tagged

from .test_eai_rt_valuation import TestEaiRtValuationBase


@tagged('post_install', '-at_install', 'eai_rt')
class TestEaiRtLanded(TestEaiRtValuationBase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acc_lc = cls.env['account.account'].create({
            'code': '611399', 'name': 'Biaya Jaga Stok (dikapitalisasi)', 'account_type': 'expense',
            'company_ids': [Command.link(cls.company.id)],
        })
        cls.lc_product = cls.env['product.product'].create({
            'name': 'Premium 0,4%', 'type': 'service', 'landed_cost_ok': True,
        })

    def _landed_cost(self, picking, amount):
        lc = self.env['stock.landed.cost'].create({
            'picking_ids': [Command.set(picking.ids)],
            'cost_lines': [Command.create({
                'product_id': self.lc_product.id,
                'name': 'Premium',
                'price_unit': amount,
                'split_method': 'equal',
                'account_id': self.acc_lc.id,
            })],
        })
        lc.compute_landed_cost()
        lc.button_validate()
        return lc

    def test_landed_cost_all_in_stock(self):
        po = self._po(2, 1000)
        self._bill(po)
        receipt = self._receive(po)
        lc = self._landed_cost(receipt, 100)
        self.assertFalse(lc.account_move_id, "Jurnal landed cost standar tidak dibuat untuk kategori bertanda")
        self.assertAlmostEqual(receipt.move_ids.value, 2100)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), 2100)
        self.assertAlmostEqual(self._balance(self.acc_lc), -100)
        self.assertAlmostEqual(self._balance(self.acc_input), 0)

    def test_landed_cost_partly_sold(self):
        po = self._po(2, 1000)
        self._bill(po)
        receipt = self._receive(po)
        so = self._so(1, 1500)
        self._deliver(so)
        self._landed_cost(receipt, 100)
        # Odoo 19: hanya porsi qty yang masih di stok (1 dari 2) yang dikapitalisasi.
        # GL persediaan = nilai valuasi; porsi barang terjual tetap beban di akun landed cost.
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), self.lm10.total_value, places=2)
        self.assertAlmostEqual(self._balance(self.acc_stock, self.lm10), 1050)
        self.assertAlmostEqual(self._balance(self.acc_lc), -50)
        invoice = so._create_invoices()
        invoice.action_post()
        self.assertAlmostEqual(self._balance(self.acc_output), 0, places=2)

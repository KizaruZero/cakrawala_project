import base64
from datetime import date
import io
from zipfile import ZipFile

from lxml import etree

from odoo import Command
from odoo.tests import tagged

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestRentalContractAppendix(RentalBillingEngineInvoiceCommon):
    def _xml(self, order):
        with ZipFile(io.BytesIO(base64.b64decode(order.contract_file))) as archive:
            return etree.fromstring(archive.read('word/document.xml'))

    def _text(self, order):
        return ''.join(self._xml(order).xpath('//w:t/text()', namespaces={
            'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        }))

    def test_frequency_and_payment_terms_follow_order_not_template_example(self):
        for value, label in (
            ('monthly', 'Bulanan'), ('per_3_months', 'Per 3 bulan'),
            ('per_6_months', 'Per 6 bulan'), ('yearly', 'Tahunan'),
            ('as_duration', 'Sesuai durasi sewa'),
        ):
            with self.subTest(frequency=value):
                order = self._order(invoicing_cycle_period=value)
                data = order._contract_appendix_context()
                self.assertEqual(data['appendix_payment_frequency'], label)
                self.assertEqual(data['appendix_payment_terms'], self.payment_term.name)

    def test_appendix_uses_contract_start_number_and_dynamic_customer(self):
        self.partner.name = 'PT Customer & Rental <QA>'
        order = self._order(
            contract_number='No.0888/PS/CRS/IX/2025',
            contract_start_date=date(2025, 9, 16), contract_end_date=date(2028, 9, 15),
            attention_up='PIC & Customer', invoicing_cycle_period='per_3_months',
        )
        order.action_create_contract()
        text = self._text(order)
        self.assertIn('LAMPIRAN PERJANJIAN SEWA TANGGAL 16 SEPTEMBER 2025 No.0888/PS/CRS/IX/2025', text)
        self.assertIn('Jakarta pada tanggal 16 September 2025.', text)
        self.assertIn(self.partner.name, text)
        self.assertIn('PIC & Customer', text)
        self.assertNotIn('PT Transgo', text)
        self.assertNotIn('Muhammad Qolbu', text)
        self.assertNotIn('No.No.', text)
        self.assertNotIn('{{', text)
        self.assertNotIn('{%', text)
        self.assertIn('Per 3 bulan', text)
        self.assertIn(self.payment_term.name, text)
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        root = self._xml(order)
        self.assertTrue(root.xpath('//w:p[w:pPr/w:pageBreakBefore][.//w:t[contains(., "LAMPIRAN")]]', namespaces=ns))
        self.assertEqual(len(root.xpath('//w:tbl[w:tr/w:tc//w:t[text()="Harga Sewa Rp."]]', namespaces=ns)), 1)
        order.action_create_contract()
        self.assertEqual(self._text(order).count('LAMPIRAN PERJANJIAN SEWA'), 1)

    def test_order_lines_not_input_orders_supply_vehicle_rows(self):
        self.unit_account.name = 'B 1234 ABC'
        order = self._order(order_line=[
            Command.create({**self._line_values(date(2026, 1, 7)), 'sequence': 20}),
            Command.create({**self._line_values(False), 'sequence': 10}),
            Command.create({'display_type': 'line_note', 'name': 'Not a vehicle'}),
        ])
        before = order.order_line.read(['price_subtotal', 'price_total', 'tax_ids'])
        rows = order._contract_appendix_context()['appendix_vehicle_rows']
        self.assertEqual(len(rows), 2)
        self.assertEqual([row['number'] for row in rows], [1, 2])
        self.assertEqual(rows[0]['start'], order.contract_start_date.strftime('%d-%m-%Y'))
        self.assertEqual(rows[1]['start'], '07-01-2026')
        self.assertEqual(rows[0]['end'], order.contract_end_date.strftime('%d-%m-%Y'))
        self.assertEqual(rows[0]['location'], self.location.name)
        self.assertEqual(rows[0]['plate'], 'B 1234 ABC')
        self.assertEqual(rows[0]['type'], self.product.with_context(display_default_code=False).display_name)
        self.assertEqual(order.order_line.read(['price_subtotal', 'price_total', 'tax_ids']), before)

    def test_amounts_follow_native_discounted_sale_taxes(self):
        taxes = self.env['account.tax']
        for name, amount in [('PPN 11%', 11), ('PPh 23', -2)]:
            group = self.env['account.tax.group'].create({'name': name})
            taxes |= self.env['account.tax'].create({
                'name': name, 'amount': amount, 'type_tax_use': 'sale', 'tax_group_id': group.id,
            })
        order = self._order(order_line=[Command.create({
            **self._line_values(date(2026, 1, 5)), 'price_unit': 1000000,
            'discount': 10, 'tax_ids': [Command.set(taxes.ids)],
        })])
        row = order._contract_appendix_context()['appendix_vehicle_rows'][0]
        def number(value):
            return float(value.replace('.', '').replace(',', '.'))
        self.assertEqual(number(row['dpp']), order.order_line.price_subtotal)
        self.assertEqual(number(row['total']), order.order_line.price_total)
        self.assertAlmostEqual(number(row['ppn']), 99000)
        self.assertAlmostEqual(number(row['pph']), 18000)
        self.assertAlmostEqual(number(row['total']), number(row['dpp']) + number(row['ppn']) - number(row['pph']))

    def test_reference_insurance_and_miscellaneous_clauses_remain(self):
        order = self._order()
        order.action_create_contract()
        text = self._text(order).split('LAMPIRAN PERJANJIAN SEWA', 1)[1]
        for value in ('300.000', '100.000.000', '5.000.000', '10.000.000',
                      '40.000km', '2 tahun pemakaian', 'Kecurian Total', 'huru-hara'):
            self.assertIn(value, text)

    def test_no_placeholder_transgo_vehicle_rows_when_order_lines_empty(self):
        order = self._order(order_line=[])
        self.assertEqual(order._contract_appendix_context()['appendix_vehicle_rows'], [])
        order.action_create_contract()
        self.assertNotIn('CALYA', self._text(order))

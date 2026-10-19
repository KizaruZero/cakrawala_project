import base64
import io
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from lxml import etree, html

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools.pdf import PdfReader


REPORT = 'x_purchase_report.report_purchase_order_custom_action'


@tagged('post_install', '-at_install')
class TestPurchaseInputOrderReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={
            **cls.env.context, 'tracking_disable': True,
            'mail_create_nosubscribe': True, 'lang': 'en_US', 'tz': 'Asia/Jakarta',
        })
        cls.company = cls.env.company
        cls.company.write({
            'name': 'PT CAKRAWALA RENTALINDO SEJAHTERA',
            'currency_id': cls.env.ref('base.IDR').id, 'city': 'Jakarta',
            'po_sign': 'Bumina Elizabeth, Tjhin',
            'logo': base64.b64encode(
                b'<svg xmlns="http://www.w3.org/2000/svg" width="550" height="130">'
                b'<text x="5" y="85" fill="#0873bf" font-size="42" font-family="sans-serif">CAKRAWALA RENT</text>'
                b'<text x="95" y="115" font-size="14">Best Solution for Your Transportation</text></svg>'
            ),
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'PT. Plaza Auto Prima', 'street': 'Jl. Panjang No. 25 Sunrise Garden',
            'city': 'DKI Jakarta', 'country_id': cls.env.ref('base.id').id,
        })
        cls.leasing = cls.env['res.partner'].create({
            'name': 'Toyota Astra Financial', 'street': 'LEASING ADDRESS MUST NOT PRINT',
            'phone': '081200099988', 'city': 'LEASING CITY MUST NOT PRINT',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'TOYOTA INNOVA ZENIX (V 2.0 CVT, 2026)',
            'type': 'consu', 'is_vehicle': True, 'purchase_ok': True,
            'supplier_taxes_id': [Command.clear()],
        })
        cls.payment_term = cls.env['account.payment.term'].create({
            'name': 'Existing transaction payment term - unchanged',
            'line_ids': [Command.create({'value': 'percent', 'value_amount': 100, 'nb_days': 30})],
        })

    def _order(self, quantities=(3,), state='purchase', price=484000000, fixed_discount=35000000, taxes=None):
        order = self.env['purchase.order'].create({
            'partner_id': self.partner.id, 'company_id': self.company.id,
            'currency_id': self.company.currency_id.id,
            'date_order': datetime(2026, 10, 15, 3),
            'leasing_partner_id': self.leasing.id, 'payment_term_id': self.payment_term.id,
            'note': '<p>Notes: Menggunakan No. Polisi / Plat daerah Jakarta + Uji Emisi</p>'
                    '<p>Syarat-Syarat Kelengkapan Penagihan</p>'
                    '<ol><li>Kwitansi bermaterai</li><li>SPT dan rekening</li><li>Faktur Pajak</li></ol>',
        })
        for index, quantity in enumerate(quantities):
            source = self.env['purchase.order.input.line'].create({
                'order_id': order.id, 'product_id': self.product.id,
                'name': 'RPC/2026/10-00033 - ' + self.product.display_name + '\nInput note %s' % (index + 1),
                'quantity': quantity, 'price_unit': price, 'sequence': 10 + index,
            })
            self.env['purchase.order.line'].create([{
                'order_id': order.id, 'input_line_id': source.id,
                'product_id': self.product.id,
                'name': 'Products-only generated description must not print',
                'product_uom_id': self.product.uom_id.id, 'product_qty': 1,
                'price_unit': price, 'fixed_discount': fixed_discount,
                'date_planned': datetime(2026, 10, 20, 5),
                'tax_ids': [Command.set(taxes.ids)] if taxes else [Command.clear()],
            } for _ in range(quantity)])
        order.write({'state': state, 'effective_date': datetime(2026, 10, 15, 5)})
        return order

    def _html(self, orders):
        content, _ = self.env['ir.actions.report']._render_qweb_html(REPORT, orders.ids)
        return html.fromstring(content)

    def _products_order(self, **values):
        order = self._order(**values)
        order.order_line.input_line_id = False
        order.input_line_ids.unlink()
        order.order_line.name = (
            'RPC/2026/10-00033 - ' + self.product.display_name
            + '\nProducts fallback delivery note'
        )
        return order

    def _pdf(self, order, name):
        report_model = type(self.env['ir.actions.report'])
        prepare = report_model._prepare_html
        cache = {}

        def inline(reports, content):
            root = html.fromstring(content)
            for node in root.xpath('//link[@rel="stylesheet"]'):
                url = node.get('href')
                if url not in cache:
                    bundle, rtl, _kind, autoprefix = reports.env['ir.asset']._parse_bundle_name(url.rsplit('/', 1)[-1], False)
                    assets = reports.env['ir.qweb']._get_asset_bundle(bundle, css=True, js=False, rtl=rtl, autoprefix=autoprefix).css()
                    cache[url] = '\n'.join(asset.raw.decode() for asset in assets)
                node.tag = 'style'
                node.attrib.clear()
                node.text = cache[url]
            return etree.tostring(root, encoding='unicode', method='html')

        def inline_prepare(reports, content, report_model=False):
            bodies, ids, header, footer, args = prepare(reports, content, report_model=report_model)
            # Native compiled CSS is not committed during tests; inline those
            # exact assets only for the test, leaving production rendering intact.
            return [inline(reports, body) for body in bodies], ids, inline(reports, header), inline(reports, footer), args

        with patch.object(report_model, '_prepare_html', inline_prepare):
            content, kind = self.env['ir.actions.report'].with_context(force_report_rendering=True)._render_qweb_pdf(REPORT, res_ids=order.ids)
        self.assertEqual(kind, 'pdf')
        if os.environ.get('PO_PDF_QA_DIR'):
            Path(os.environ['PO_PDF_QA_DIR'], name + '.pdf').write_bytes(content)
        return PdfReader(io.BytesIO(content))

    def test_input_rows_aggregate_generated_discounts_amounts_and_preserve_data(self):
        order = self._order()
        before = order.read(['amount_total', 'payment_term_id', 'state'])
        lines_before = order.order_line.read(['name', 'price_unit', 'fixed_discount', 'product_qty', 'price_total'])
        inputs_before = order.input_line_ids.read(['name', 'quantity', 'price_unit'])
        rows = order._po_report_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['quantity'], 3)
        self.assertEqual(rows[0]['price_unit'], 484000000)
        self.assertEqual(rows[0]['fixed_discount'], 105000000)
        self.assertEqual(rows[0]['amount'], 1347000000)
        self.assertEqual(rows[0]['amount'], order.amount_total)
        self.assertIn('Input note 1', rows[0]['description'])
        self.assertNotIn('RPC/', rows[0]['description'])
        self._html(order)
        self.assertEqual(order.read(['amount_total', 'payment_term_id', 'state']), before)
        self.assertEqual(order.order_line.read(['name', 'price_unit', 'fixed_discount', 'product_qty', 'price_total']), lines_before)
        self.assertEqual(order.input_line_ids.read(['name', 'quantity', 'price_unit']), inputs_before)

    def test_same_variant_input_rows_not_merged_and_percentage_discount_preserved(self):
        order = self._order(quantities=(2, 1), fixed_discount=0)
        order.order_line.write({'discount': 10})
        rows = order._po_report_rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual([row['quantity'] for row in rows], [2, 1])
        self.assertEqual([row['fixed_discount'] for row in rows], [96800000, 48400000])
        self.assertEqual(sum(row['amount'] for row in rows), order.amount_total)

    def test_taxed_amounts_and_weighted_actual_vendor_price(self):
        tax = self.env['account.tax'].create({'name': 'PO Test PPN', 'amount': 11, 'type_tax_use': 'purchase'})
        order = self._order(quantities=(2,), price=1000000, fixed_discount=100000, taxes=tax)
        order.order_line[-1].price_unit = 1200000
        row = order._po_report_rows()[0]
        self.assertEqual(row['price_unit'], 1100000)
        self.assertEqual(row['fixed_discount'], 200000)
        self.assertEqual(row['amount'], order.amount_total)
        self.assertEqual(row['amount'], 2220000)

    def test_expected_arrival_and_name_only_leasing_next_to_each_other(self):
        root = self._html(self._order(quantities=(1,)))
        block = root.xpath('//table[@name="po_arrival_leasing"]')[0]
        text = ' '.join(block.text_content().split())
        self.assertIn('Expected Arrival Date: 20 Oktober 2026', text)
        self.assertNotIn('15 Oktober 2026', text)
        self.assertIn('Leasing Partner: Toyota Astra Financial', text)
        self.assertEqual(len(block.xpath('./tr/td | ./tbody/tr/td')), 2)
        self.assertNotIn('LEASING ADDRESS MUST NOT PRINT', root.text_content())
        self.assertNotIn('081200099988', root.text_content())
        self.assertNotIn('Confirm Receipt Date', root.text_content())
        self.assertIn('Two weeks after delivery unit', root.text_content())
        self.assertFalse(root.xpath('//*[local-name()="circle"]'))

    def test_empty_input_order_falls_back_to_products_and_preserves_data(self):
        order = self._products_order(quantities=(2,))
        before = order.read(['amount_total', 'payment_term_id', 'state', 'input_line_ids'])
        line_fields = ['name', 'price_unit', 'fixed_discount', 'product_qty', 'price_total']
        lines_before = order.order_line.read(line_fields)
        rows = order._po_report_rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual([row['purchase_line_id'] for row in rows], order.order_line.ids)
        self.assertEqual([row['quantity'] for row in rows], [1, 1])
        self.assertEqual([row['price_unit'] for row in rows], [484000000, 484000000])
        self.assertEqual([row['fixed_discount'] for row in rows], [35000000, 35000000])
        self.assertEqual(sum(row['amount'] for row in rows), order.amount_total)
        self.assertTrue(all(not row['input_line_id'] for row in rows))
        root = self._html(order)
        self.assertEqual(len(root.xpath('//tr[@name="po_input_order_row"]')), 2)
        self.assertIn('Products fallback delivery note', root.text_content())
        self.assertNotIn('RPC/2026', root.text_content())
        self.assertFalse(root.xpath('//tr[@name="po_other_amounts"]'))
        self.assertEqual(order.read(['amount_total', 'payment_term_id', 'state', 'input_line_ids']), before)
        self.assertEqual(order.order_line.read(line_fields), lines_before)

    def test_products_fallback_preserves_taxes_discounts_quantities_and_sequence(self):
        tax = self.env['account.tax'].create({
            'name': 'Products Fallback PPN', 'amount': 11, 'type_tax_use': 'purchase',
        })
        order = self._products_order(quantities=(2,), price=1000000, fixed_discount=0, taxes=tax)
        first, second = order.order_line
        first.write({'sequence': 30, 'product_qty': 2, 'discount': 10})
        second.write({'sequence': 5, 'price_unit': 1200000, 'fixed_discount': 100000})
        rows = order._po_report_rows()
        self.assertEqual([row['purchase_line_id'] for row in rows], [second.id, first.id])
        self.assertEqual([row['quantity'] for row in rows], [1, 2])
        self.assertEqual([row['price_unit'] for row in rows], [1200000, 1000000])
        self.assertEqual([row['fixed_discount'] for row in rows], [100000, 200000])
        self.assertEqual([row['amount'] for row in rows], [1221000, 1998000])
        self.assertEqual(sum(row['amount'] for row in rows), order.amount_total)

    def test_products_fallback_without_input_order_field(self):
        order = self._products_order(quantities=(1,))
        expected = order._po_report_rows()
        fields_without_input = {name: field for name, field in order._fields.items() if name != 'input_line_ids'}
        with patch.object(type(order), '_fields', fields_without_input):
            self.assertEqual(order._po_report_rows(), expected)

    def test_products_fallback_uses_real_items_not_sections_notes_or_downpayments(self):
        order = self._products_order(quantities=(1,), state='draft')
        real_line = order.order_line
        self.env['purchase.order.line'].create([
            {'order_id': order.id, 'display_type': 'line_section', 'name': 'Section only', 'product_qty': 0},
            {'order_id': order.id, 'display_type': 'line_note', 'name': 'Note only', 'product_qty': 0},
            {
                'order_id': order.id, 'product_id': self.product.id,
                'name': 'Zero quantity item', 'product_qty': 0,
                'product_uom_id': self.product.uom_id.id, 'price_unit': 100000,
                'date_planned': datetime(2026, 10, 20, 5), 'tax_ids': [Command.clear()],
            },
            {
                'order_id': order.id, 'product_id': self.product.id,
                'name': 'Down payment line', 'product_qty': 1, 'is_downpayment': True,
                'product_uom_id': self.product.uom_id.id, 'price_unit': 100000,
                'date_planned': datetime(2026, 10, 20, 5), 'tax_ids': [Command.clear()],
            },
        ])
        rows = order._po_report_rows()
        self.assertEqual([row['purchase_line_id'] for row in rows], real_line.ids)
        root = self._html(order)
        self.assertIn('Other PO Amounts', root.text_content())
        for hidden in ('Section only', 'Note only', 'Zero quantity item', 'Down payment line'):
            self.assertNotIn(hidden, root.text_content())

    def test_mixed_batch_selects_input_or_products_for_each_po(self):
        input_order = self._order(quantities=(2,))
        products_order = self._products_order(quantities=(2,))
        reports = self.env['report.x_purchase_report.report_purchase_order_custom']
        values = reports._get_report_values((input_order | products_order).ids)
        self.assertEqual(len(values['po_report_rows'][input_order.id]), 1)
        self.assertEqual(len(values['po_report_rows'][products_order.id]), 2)
        self.assertEqual(values['po_report_other_amounts'], {input_order.id: 0, products_order.id: 0})
        root = self._html(input_order | products_order)
        self.assertEqual(len(root.xpath('//tr[@name="po_input_order_row"]')), 3)

    def test_incomplete_input_and_mismatched_generated_product_rejected(self):
        order = self._order(quantities=(2,), state='draft')
        order.order_line[-1].unlink()
        with self.assertRaisesRegex(UserError, 'Generate all Order Lines'):
            self._html(order)
        complete = self._order(quantities=(1,))
        other = self.product.copy({'name': 'Different Fleet Variant'})
        complete.order_line.product_id = other
        with self.assertRaisesRegex(UserError, 'does not match Input Order'):
            self._html(complete)

    def test_input_order_sequence_controls_print_order(self):
        order = self._order(quantities=(2, 1))
        first, second = order.input_line_ids
        first.sequence = 30
        second.sequence = 5
        self.assertEqual([row['input_line_id'] for row in order._po_report_rows()], [second.id, first.id])

    def test_unlinked_other_po_amounts_disclosed_without_extra_product_rows(self):
        order = self._order(quantities=(1,))
        self.env['purchase.order.line'].create({
            'order_id': order.id, 'name': 'Products-only extra must not print',
            'product_id': self.product.id, 'product_qty': 1,
            'product_uom_id': self.product.uom_id.id, 'price_unit': 100000,
            'date_planned': datetime(2026, 10, 20, 5), 'tax_ids': [Command.clear()],
        })
        root = self._html(order)
        self.assertEqual(len(root.xpath('//tr[@name="po_input_order_row"]')), 1)
        self.assertIn('Other PO Amounts', root.text_content())
        self.assertNotIn('Products-only extra', root.text_content())
        self.assertEqual(order.amount_total, 449100000)

    def test_rpc_in_middle_and_separate_paragraph_removed_but_notes_retained(self):
        order = self._order(quantities=(1,))
        order.input_line_ids.name = 'Vehicle RPC/2026/10-00033 - with service\nRPC/2026/10-00034\nKeep this note'
        text = order._po_report_rows()[0]['description']
        self.assertEqual(text, 'Vehicle with service\nKeep this note')

    def test_pdf_layout_purchase_order_and_draft_watermark(self):
        order = self._order(quantities=(3,))
        pdf = self._pdf(order, 'purchase-order-input')
        self.assertEqual(len(pdf.pages), 1)
        text = ' '.join(pdf.pages[0].extract_text().split())
        for expected in ('Purchase Order #', 'Expected Arrival Date:', '20 Oktober 2026',
                         'Toyota Astra Financial', 'Two weeks after delivery unit', '1,347,000,000'):
            self.assertIn(expected, text)
        for forbidden in ('RPC/2026', 'Products-only generated', 'LEASING ADDRESS', '081200099988', 'Confirm Receipt Date'):
            self.assertNotIn(forbidden, text)
        self.assertFalse(self._html(order).xpath('//img[@alt="DRAFT"]'))
        order.state = 'waiting_approval'
        root = self._html(order)
        self.assertTrue(root.xpath('//img[@alt="DRAFT"]'))
        self.assertIn('Request for Quotation #', root.text_content())
        pdf = self._pdf(order, 'purchase-order-draft')
        self.assertEqual(len(pdf.pages), 1)

    def test_pdf_layout_products_fallback(self):
        order = self._products_order(quantities=(2,))
        pdf = self._pdf(order, 'purchase-order-products-fallback')
        self.assertEqual(len(pdf.pages), 1)
        text = ' '.join(pdf.pages[0].extract_text().split())
        for expected in ('Purchase Order #', 'Products fallback delivery note', 'Expected Arrival Date:',
                         'Toyota Astra Financial', 'Two weeks after delivery unit', '898,000,000'):
            self.assertIn(expected, text)
        self.assertEqual(text.count('Products fallback delivery note'), 2)
        self.assertNotIn('RPC/2026', text)
        self.assertNotIn('Other PO Amounts', text)

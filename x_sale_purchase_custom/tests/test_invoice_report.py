import base64
import io
import os
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from lxml import etree, html

from odoo import Command
from odoo.tests import TransactionCase, tagged
from odoo.tools.pdf import PdfReader

from .test_billing_engine import TestRentalBillingEngine
from .test_billing_engine_invoices import TestRentalBillingEngineInvoices


@tagged('post_install', '-at_install')
class TestCakrawalaInvoiceReport(TransactionCase):
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
            'currency_id': cls.env.ref('base.IDR').id,
            'country_id': cls.env.ref('base.id').id,
            'street': 'COMPANY ADMINISTRATIVE ADDRESS MUST NOT PRINT',
            'logo': base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg" width="620" height="150"><text x="5" y="90" fill="#0676c4" font-size="48" font-family="sans-serif">CAKRAWALA RENT</text><text x="120" y="125" font-size="15">Best Solution for Your Transportation</text></svg>'),
        })
        cls.income_account = cls.env['account.account'].create({
            'name': 'Invoice Layout Test Income', 'code': '799990101',
            'account_type': 'income', 'company_ids': [Command.set(cls.company.ids)],
        })
        cls.receivable_account = cls.env['account.account'].create({
            'name': 'Invoice Layout Test Receivable', 'code': '799990102',
            'account_type': 'asset_receivable', 'reconcile': True,
            'company_ids': [Command.set(cls.company.ids)],
        })
        cls.journal = cls.env['account.journal'].create({
            'name': 'Invoice Layout Test Sales', 'code': 'LAYT', 'type': 'sale',
            'company_id': cls.company.id, 'default_account_id': cls.income_account.id,
        })
        cls.payment_term = cls.env['account.payment.term'].create({
            'name': '30 Days', 'company_id': cls.company.id,
            'line_ids': [Command.create({'value': 'percent', 'value_amount': 100, 'nb_days': 30})],
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'PT ARUTMIN INDONESIA, Indri - 01',
            'street': 'BAKRIE TOWER LANTAI 14, KOMP. RASUNA',
            'street2': 'JL. HR RASUNA SAID RT.002 RW.05', 'city': 'Jakarta',
            'country_id': cls.env.ref('base.id').id,
            'property_account_receivable_id': cls.receivable_account.id,
            'property_payment_term_id': cls.payment_term.id,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'TOYOTA INNOVA ZENIX (V 2.0 CVT, 2026)',
            'type': 'consu', 'rent_ok': True, 'list_price': 9500000,
            'property_account_income_id': cls.income_account.id,
            'taxes_id': [Command.clear()],
        })
        cls.stamp_product = cls.env['product.product'].create({
            'name': 'Biaya Materai', 'type': 'service',
            'property_account_income_id': cls.income_account.id,
            'taxes_id': [Command.clear()],
        })
        cls.company.rental_invoice_stamp_product_id = cls.stamp_product
        cls.rental_type = cls.env['sale.rental.type'].create({'name': 'Invoice Layout Test Rental'})
        cls.plan = cls.env['account.analytic.plan'].create({'name': 'Invoice Layout Test Units'})
        cls.unit_account = cls.env['account.analytic.account'].create({
            'name': 'FN-2026-0000164', 'plan_id': cls.plan.id, 'company_id': cls.company.id,
        })
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'Invoice Layout Test Brand'})
        model = cls.env['fleet.vehicle.model'].create({'name': 'Innova Test', 'brand_id': brand.id})
        cls.vehicle = cls.env['fleet.vehicle'].create({
            'model_id': model.id, 'license_plate': 'B 1234 ABC', 'company_id': cls.company.id,
        })
        cls.order_model = cls.env['sale.order']

    _line_values = TestRentalBillingEngine._line_values
    _rows = TestRentalBillingEngine._rows
    _order = TestRentalBillingEngineInvoices._order

    def _invoice(self, units=1, legacy=False, posted=False, taxes=False):
        lines = [Command.create(self._line_values(
            date(2026, 10, 15), name='RPC/2026/10-00033 - ' + self.product.name,
            fleet_vehicle_id=self.vehicle.id, price_unit=9500000,
            tax_ids=[Command.set(taxes.ids)] if taxes else [Command.clear()],
        )) for _ in range(units)]
        order = self._order(start=datetime(2026, 10, 15, 5), months=1, order_line=lines)
        invoice = order._generate_billing_engine_invoices(current_month_only=False)
        invoice.write({'ref': 'HIDDEN-REFERENCE', 'delivery_date': date(2026, 10, 15)})
        if legacy:
            rental_lines = invoice.invoice_line_ids.filtered(lambda line: not line.x_is_stamp_duty)
            rental_lines.write({
                'name': 'RPC/2026/10-00033 - ' + self.product.name + '\nUnit plate No: FN-2026-0000164\n2026-10-15 - 2026-11-14',
                'x_plate_number': 'FN-2026-0000164',
            })
        if posted:
            invoice.action_post()
        return order, invoice

    def _html(self, invoice):
        content, _ = self.env['ir.actions.report']._render_qweb_html('account.report_invoice', invoice.ids)
        return html.fromstring(content)

    def _pdf(self, invoice, name):
        model = type(self.env['ir.actions.report'])
        prepare = model._prepare_html
        css_cache = {}

        def inline(reports, content):
            root = html.fromstring(content)
            for node in root.xpath('//link[@rel="stylesheet"]'):
                url = node.get('href')
                if url not in css_cache:
                    bundle, rtl, _kind, autoprefix = reports.env['ir.asset']._parse_bundle_name(url.rsplit('/', 1)[-1], False)
                    assets = reports.env['ir.qweb']._get_asset_bundle(bundle, css=True, js=False, rtl=rtl, autoprefix=autoprefix).css()
                    css_cache[url] = '\n'.join(asset.raw.decode() for asset in assets)
                node.tag = 'style'
                node.attrib.clear()
                node.text = css_cache[url]
            return etree.tostring(root, encoding='unicode', method='html')

        def prepare_inline(reports, content, report_model=False):
            bodies, ids, header, footer, args = prepare(reports, content, report_model=report_model)
            return [inline(reports, body) for body in bodies], ids, inline(reports, header), inline(reports, footer), args

        with patch.object(model, '_prepare_html', prepare_inline):
            content, kind = self.env['ir.actions.report'].with_context(force_report_rendering=True)._render_qweb_pdf(
                'account.account_invoices', res_ids=invoice.ids,
            )
        self.assertEqual(kind, 'pdf')
        if os.environ.get('INVOICE_PDF_QA_DIR'):
            Path(os.environ['INVOICE_PDF_QA_DIR'], name + '.pdf').write_bytes(content)
        return PdfReader(io.BytesIO(content))

    def test_real_stamp_charge_once_and_existing_invoices_untouched(self):
        order, invoice = self._invoice()
        stamp = invoice.invoice_line_ids.filtered('x_is_stamp_duty')
        self.assertEqual(len(stamp), 1)
        self.assertEqual(stamp.price_subtotal, 10000)
        self.assertEqual(stamp.account_id, self.income_account)
        self.assertFalse(stamp.sale_line_ids)
        self.assertEqual(invoice.amount_total, 9510000)
        before = invoice.read(['amount_total', 'invoice_line_ids'])
        self.assertFalse(order._generate_billing_engine_invoices(current_month_only=False))
        self.assertEqual(invoice.read(['amount_total', 'invoice_line_ids']), before)
        invoice.action_post()
        before = invoice.read(['state', 'name', 'amount_total', 'invoice_line_ids'])
        self.assertFalse(order._generate_billing_engine_invoices(current_month_only=False))
        self.assertEqual(invoice.read(['state', 'name', 'amount_total', 'invoice_line_ids']), before)

    def test_stamp_not_retrofitted_and_late_unit_not_double_charged(self):
        self.company.rental_invoice_stamp_product_id = False
        order, invoice = self._invoice()
        self.company.rental_invoice_stamp_product_id = self.stamp_product
        self.env['sale.order.line'].create({
            'order_id': order.id,
            **self._line_values(date(2026, 10, 15), price_unit=9500000),
        })
        self.assertEqual(order._generate_billing_engine_invoices(current_month_only=False), invoice)
        self.assertFalse(invoice.invoice_line_ids.filtered('x_is_stamp_duty'))
        other, charged = self._invoice()
        self.env['sale.order.line'].create({'order_id': other.id, **self._line_values(date(2026, 10, 15))})
        other._generate_billing_engine_invoices(current_month_only=False)
        self.assertEqual(len(charged.invoice_line_ids.filtered('x_is_stamp_duty')), 1)

    def test_actual_plate_and_legacy_print_do_not_change_posted_lines(self):
        _order, invoice = self._invoice(legacy=True, posted=True)
        line = invoice.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty)
        before = line.read(['name', 'x_plate_number', 'balance'])
        description = line._rental_invoice_print_description()
        self.assertIn('B 1234 ABC', description)
        self.assertIn('15-10-2026 - 14-11-2026', description)
        self.assertNotIn('RPC/', description)
        self.assertNotIn('Unit plate No', description)
        self.assertNotIn('FN-2026', description)
        self.assertEqual(line.read(['name', 'x_plate_number', 'balance']), before)
        line.sale_line_ids.fleet_vehicle_id = False
        self.assertNotIn('FN-2026', line._rental_invoice_print_description())

    def test_indonesian_words_include_stamp_and_withholding(self):
        group = self.env['account.tax.group'].create({'name': 'PPN 11%', 'country_id': self.company.account_fiscal_country_id.id})
        ppn = self.env['account.tax'].create({'name': 'PPN 11%', 'amount': 11, 'type_tax_use': 'sale', 'tax_group_id': group.id})
        group_pph = self.env['account.tax.group'].create({'name': 'PPh 23', 'country_id': self.company.account_fiscal_country_id.id})
        pph = self.env['account.tax'].create({'name': 'PPh 23', 'amount': -2, 'type_tax_use': 'sale', 'tax_group_id': group_pph.id})
        _order, invoice = self._invoice(taxes=ppn | pph)
        self.assertEqual(invoice.amount_total, 10365000)
        self.assertEqual(invoice._invoice_amount_words_indonesian(), 'Sepuluh juta tiga ratus enam puluh lima ribu rupiah')
        root = self._html(invoice)
        table = root.xpath('//table[@name="invoice_line_table"]')[0]
        self.assertFalse(table.xpath('.//th[@name="th_taxes"]'))
        self.assertFalse(table.xpath('.//td[@name="td_quantity"]//span[@t-field="line.product_uom_id"]'))
        totals = root.xpath('//div[@id="total"]')[0].text_content()
        self.assertIn('DPP', totals)
        self.assertIn('PPN 11%', totals)
        self.assertIn('PPh 23', totals)
        self.assertIn('Biaya Materai', totals)
        pdf = self._pdf(invoice, 'customer-invoice-taxed')
        self.assertEqual(len(pdf.pages), 1)
        self.assertIn('Sepuluh juta tiga ratus enam puluh lima ribu rupiah',
                      ' '.join(pdf.pages[0].extract_text().split()))

    def test_customer_invoice_pdf_layout_and_legacy_posted_data(self):
        _order, invoice = self._invoice(legacy=True, posted=True)
        before = invoice.read(['state', 'amount_total', 'invoice_line_ids'])
        root = self._html(invoice)
        self.assertFalse(root.xpath('//div[@name="origin"]'))
        self.assertFalse(root.xpath('//div[@name="reference"]'))
        self.assertEqual(root.xpath('//div[@name="customer_payment_terms"]//div')[0].text_content(), '30 Days')
        pdf = self._pdf(invoice, 'customer-invoice')
        self.assertEqual(len(pdf.pages), 1)
        text = ' '.join(pdf.pages[0].extract_text().split())
        for expected in ('PT ARUTMIN', 'B 1234 ABC', '15-10-2026 - 14-11-2026',
                         'Terbilang:', '1685656789', 'DPP', 'Biaya Materai',
                         'finance@cakrawalarentalindo.com', 'Hormat Kami,', 'Alvina Jeriwati', 'General Manager'):
            self.assertIn(expected, text)
        for forbidden in ('COMPANY ADMINISTRATIVE', 'RPC/2026', 'FN-2026', 'Unit plate No', 'HIDDEN-REFERENCE', 'Source', 'Untaxed Amount'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(invoice.read(['state', 'amount_total', 'invoice_line_ids']), before)

    def test_stored_four_invoice_terms_preserved_in_posted_pdf(self):
        _order, invoice = self._invoice(legacy=True)
        clauses = [
            'Pembayaran akan dianggap sah apabila sudah diterima di rekening PT Cakrawala Rentalindo Sejahtera.',
            'Silakan melakukan konfirmasi melalui email finance@cakrawalarentalindo.com.',
            'Apabila terdapat kesalahan pada invoice yang sudah diterima kami tidak bisa membatalkan invoice tersebut dan hanya bisa merevisi untuk periode berikutnya.',
            'PPH 23 dipotong dengan tarif 2% dari nilai invoice (tidak termasuk PPN), bukti pemotongan PPH 23 agar dikirim melalui email finance@cakrawalarentalindo.com.',
        ]
        invoice.narration = '<p><strong>Term and Conditions:</strong></p><ul>%s</ul>' % ''.join(
            '<li>%s</li>' % clause for clause in clauses
        )
        invoice.action_post()
        before = invoice.read(['narration', 'state', 'name', 'amount_total', 'invoice_line_ids'])
        terms = self._html(invoice).xpath('//div[@name="customer_invoice_terms"]')[0]
        self.assertEqual(len(terms.xpath('.//li')), 4)
        self.assertEqual([' '.join(item.text_content().split()) for item in terms.xpath('.//li')], clauses)
        self.assertEqual(terms.text_content().count('Term and Conditions:'), 1)
        pdf = self._pdf(invoice, 'customer-invoice-four-terms')
        self.assertEqual(len(pdf.pages), 1)
        text = ' '.join(pdf.pages[0].extract_text().split())
        for clause in clauses:
            self.assertIn(clause, text)
        self.assertEqual(invoice.read(['narration', 'state', 'name', 'amount_total', 'invoice_line_ids']), before)

    def test_custom_invoice_terms_not_limited_or_replaced_by_defaults(self):
        _order, invoice = self._invoice()
        clauses = ['Customer-specific clause %s' % index for index in range(1, 6)]
        invoice.narration = '<p>Contract-specific conditions</p><ol>%s</ol>' % ''.join(
            '<li>%s</li>' % clause for clause in clauses
        )
        terms = self._html(invoice).xpath('//div[@name="customer_invoice_terms"]')[0]
        self.assertEqual(len(terms.xpath('.//li')), 5)
        self.assertEqual([' '.join(item.text_content().split()) for item in terms.xpath('.//li')], clauses)
        self.assertTrue(terms.xpath('.//ol'))
        self.assertIn('Contract-specific conditions', terms.text_content())
        self.assertNotIn('PPH 23 dipotong', terms.text_content())

    def test_empty_invoice_terms_use_all_four_defaults_without_writing_narration(self):
        _order, invoice = self._invoice()
        for empty in (False, '<p><br></p>'):
            invoice.narration = empty
            before = invoice.narration
            terms = self._html(invoice).xpath('//div[@name="customer_invoice_terms"]')[0]
            self.assertEqual(len(terms.xpath('.//li')), 4)
            self.assertIn('Pembayaran dianggap sah', terms.text_content())
            self.assertIn('Silahkan melakukan konfirmasi pembayaran', terms.text_content())
            self.assertIn('tidak bisa membatalkan invoice', terms.text_content())
            self.assertIn('PPH 23 dipotong dengan tarif 2%', terms.text_content())
            self.assertEqual(invoice.narration, before)

    def test_long_invoice_pdf_contains_all_rows_and_signature_once(self):
        _order, invoice = self._invoice(units=28)
        for index, line in enumerate(invoice.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty), 1):
            line.name += '\nService record %02d' % index
        pdf = self._pdf(invoice, 'customer-invoice-multipage')
        self.assertGreater(len(pdf.pages), 1)
        text = ' '.join(' '.join(page.extract_text().split()) for page in pdf.pages)
        for index in range(1, 29):
            self.assertIn('Service record %02d' % index, text)
        self.assertEqual(text.count('Alvina Jeriwati'), 1)
        last_page = ' '.join(pdf.pages[-1].extract_text().split())
        self.assertIn('DPP', last_page)
        self.assertIn('1685656789', last_page)
        self.assertIn('Alvina Jeriwati', last_page)

    def test_vendor_bill_retains_native_layout(self):
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.partner.id,
            'invoice_date': date(2026, 10, 15),
            'invoice_origin': 'KEEP-VENDOR-SOURCE', 'ref': 'KEEP-VENDOR-REFERENCE',
            'invoice_line_ids': [Command.create({'name': 'Vendor test line', 'quantity': 1,
                                               'price_unit': 1000, 'account_id': self.income_account.id})],
        })
        root = self._html(bill)
        self.assertFalse(root.xpath('//div[contains(@class, "o_cakrawala_invoice")]'))
        self.assertIn('KEEP-VENDOR-SOURCE', root.text_content())
        self.assertIn('KEEP-VENDOR-REFERENCE', root.text_content())
        self.assertNotIn('1685656789', root.text_content())

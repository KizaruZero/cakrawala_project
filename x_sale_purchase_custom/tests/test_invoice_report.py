import base64
import io
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date, datetime
from pathlib import Path
from statistics import median
from unittest import skipUnless
from unittest.mock import patch

from lxml import etree, html
from PIL import Image

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
        cls.location = cls.env['rpc.kota'].create({
            'name': 'Invoice Layout Test City',
            'provinsi_id': cls.env.ref('x_rental_profit_calculation.prov_dki').id,
        })
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'Invoice Layout Test Pricelist', 'currency_id': cls.company.currency_id.id,
            'company_id': cls.company.id,
        })
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

    def _invoice_with_unit_codes(self, quantity, posted=False):
        order, invoice = self._invoice(units=quantity)
        accounts = self.env['account.analytic.account'].create([{
            'name': 'FN-2026-%07d' % index,
            'plan_id': self.plan.id, 'company_id': self.company.id,
        } for index in range(1, quantity + 1)])
        rentals = invoice.invoice_line_ids.filtered(lambda line: not line.x_is_stamp_duty).sorted('id')
        for index, (line, account) in enumerate(zip(rentals, accounts), 1):
            if 'license_plate' in account._fields:
                account.license_plate = 'B %04d XYZ' % index
            line.write({
                'analytic_distribution': {str(account.id): 100},
                'x_plate_number': 'B %04d XYZ' % index,
                'name': self.product.name + '\nB %04d XYZ\n15-10-2026 - 14-11-2026' % index,
            })
        if posted:
            invoice.action_post()
        return order, invoice, accounts

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

    def _assert_totals_pdf_outline(self, reader):
        """Check real rendered borders, not just CSS declarations/HTML text."""
        with tempfile.TemporaryDirectory(prefix='invoice-border-test-') as directory:
            pdf_path = Path(directory, 'invoice.pdf')
            prefix = Path(directory, 'invoice')
            pdf_path.write_bytes(reader.stream.getvalue())
            subprocess.run([
                shutil.which('pdftoppm'), '-f', '1', '-singlefile', '-scale-to', '1800',
                '-png', str(pdf_path), str(prefix),
            ], check=True, capture_output=True, timeout=30)
            with Image.open(prefix.with_suffix('.png')) as image:
                image = image.convert('L')
                width, height = image.size
                # Thin gray print strokes are antialiased; include their pale
                # edge pixels but never the white page background.
                dark_run = re.compile(rb'[\x00-\xf0]{%d,}' % int(width * 0.25))
                horizontal = []
                for y in range(int(height * 0.1), int(height * 0.8)):
                    row = image.crop((0, y, width, y + 1)).tobytes()
                    for match in dark_run.finditer(row):
                        # Exclude the full-width product table and all text.
                        if match.start() >= width * 0.55 and match.end() - match.start() <= width * 0.45:
                            if not horizontal or y > horizontal[-1][0] + 3:
                                horizontal.append((y, match.start(), match.end() - 1))
                self.assertGreaterEqual(len(horizontal), 5, 'DPP/taxes/Total must form four closed rows')
                top, bottom = horizontal[0][0], horizontal[-1][0]
                pixels = image.load()
                for side, index in (('left', 1), ('right', 2)):
                    x = round(median(line[index] for line in horizontal))
                    covered = sum(
                        min(pixels[sample, y] for sample in range(max(0, x - 2), min(width, x + 3))) <= 240
                        for y in range(top, bottom + 1)
                    )
                    self.assertGreater(
                        covered / (bottom - top + 1), 0.95,
                        '%s totals border is missing/clipped in the rendered PDF' % side,
                    )

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
        self.assertIn('Oct 15, 2026 - Nov 14, 2026', description)
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
        for expected in ('PT ARUTMIN', 'B 1234 ABC', 'Oct 15, 2026 - Nov 14, 2026',
                         'Terbilang:', '1685656789', 'DPP', 'Biaya Materai',
                         'finance@cakrawalarentalindo.com', 'Hormat Kami,', 'Alvina Jeriwati', 'General Manager'):
            self.assertIn(expected, text)
        for forbidden in ('COMPANY ADMINISTRATIVE', 'RPC/2026', 'FN-2026', 'Unit plate No', 'HIDDEN-REFERENCE', 'Source', 'Untaxed Amount'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(invoice.read(['state', 'amount_total', 'invoice_line_ids']), before)

    def test_customer_dates_use_english_month_even_for_different_partner_language(self):
        _order, invoice = self._invoice(legacy=True)
        invoice.write({'invoice_date': date(2031, 10, 8), 'delivery_date': date(2026, 10, 16)})
        invoice.action_post()
        self.assertEqual(invoice._customer_invoice_print_date(date(2031, 10, 8)), 'Oct 8, 2031')
        self.env.ref('base.lang_id').active = True
        self.partner.lang = 'id_ID'
        root = self._html(invoice)
        self.assertIn('Oct 8, 2031', root.xpath('//div[@name="invoice_date"]')[0].text_content())
        self.assertIn('Oct 16, 2026', root.xpath('//div[@name="delivery_date"]')[0].text_content())
        due = invoice._customer_invoice_print_date(invoice.invoice_date_due)
        self.assertIn(due, root.xpath('//div[@name="due_date"]')[0].text_content())
        pdf = self._pdf(invoice, 'customer-invoice-dates')
        text = ' '.join(pdf.pages[0].extract_text().split())
        self.assertIn('Oct 8, 2031', text)
        self.assertIn('Oct 16, 2026', text)
        self.assertIn('Oct 15, 2026 - Nov 14, 2026', text)

    def test_legacy_ordinal_numeric_and_invalid_rental_ranges(self):
        _order, invoice = self._invoice()
        line = invoice.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty)
        for value in ('16th September 2026 - 15th October 2026',
                      '16-09-2026 - 15-10-2026', '2026-09-16 - 2026-10-15'):
            line.name = self.product.name + '\n' + value
            self.assertIn('Sep 16, 2026 - Oct 15, 2026', line._rental_invoice_print_description())
            self.assertIn(value, line.name)
        line.name = 'Service fee - not a date\n2026-02-31 - 2026-03-31'
        self.assertEqual(line._rental_invoice_print_description(), line.name)

    def test_identical_descriptions_group_quantity_amount_without_merging_journal_items(self):
        _order, invoice = self._invoice(units=2, legacy=True, posted=True)
        lines = invoice.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty)
        before = lines.read(['name', 'quantity', 'price_unit', 'price_subtotal', 'balance'])
        groups = invoice._customer_invoice_print_groups(invoice._get_move_lines_to_report())
        self.assertEqual(len(groups), 1)
        group = next(iter(groups.values()))
        self.assertEqual(group['quantity'], 2)
        self.assertEqual(group['price_unit'], 9500000)
        self.assertEqual(group['price_subtotal'], 19000000)
        table = self._html(invoice).xpath('//table[@name="invoice_line_table"]')[0]
        self.assertEqual(len(table.xpath('.//td[@name="account_invoice_line_name"]')), 1)
        self.assertEqual(table.xpath('.//td[@name="td_quantity"]')[0].text_content().strip(), '2.00')
        self.assertIn('19,000,000.00', table.xpath('.//td[@name="td_subtotal"]')[0].text_content())
        pdf = self._pdf(invoice, 'customer-invoice-grouped')
        text = ' '.join(pdf.pages[0].extract_text().split())
        self.assertEqual(text.count(self.product.name), 1)
        self.assertEqual(lines.read(['name', 'quantity', 'price_unit', 'price_subtotal', 'balance']), before)

    def test_grouping_keeps_periods_and_notes_but_collects_unit_identifiers(self):
        _order, invoice = self._invoice(units=2)
        lines = invoice.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty).sorted('id')
        lines[1].name = lines[1].name.replace('15-10-2026', '16-10-2026')
        self.assertEqual(len(invoice._customer_invoice_print_groups(invoice._get_move_lines_to_report())), 2)
        lines[1].name = lines[0].name
        lines[1].x_plate_number = 'B 9999 XYZ'
        lines[1].name = lines[1].name.replace('B 1234 ABC', 'B 9999 XYZ')
        groups = invoice._customer_invoice_print_groups(invoice._get_move_lines_to_report())
        self.assertEqual(len(groups), 1)
        self.assertEqual(next(iter(groups.values()))['quantity'], 2)
        lines[1].name = lines[0].name
        lines[0].sequence = 10
        lines[1].sequence = 30
        self.env['account.move.line'].create({
            'move_id': invoice.id, 'display_type': 'line_note', 'name': 'Separate contract block', 'sequence': 20,
        })
        self.assertEqual(len(invoice._customer_invoice_print_groups(invoice._get_move_lines_to_report())), 2)

    def test_one_to_ten_units_print_comma_separated_nopol_before_period(self):
        for quantity in (1, 2, 10):
            with self.subTest(quantity=quantity):
                _order, invoice, accounts = self._invoice_with_unit_codes(quantity)
                plates = ['B %04d XYZ' % index for index in range(1, quantity + 1)]
                root = self._html(invoice)
                cells = root.xpath('//td[@name="account_invoice_line_name"]')
                self.assertEqual(len(cells), 1)
                self.assertEqual(cells[0].xpath('.//span[@class="invoice_product_description"]/text()'), [self.product.name])
                self.assertEqual(cells[0].xpath('.//span[contains(@class, "invoice_analytic_code")]/text()'), plates)
                self.assertIn(', '.join(plates), cells[0].text_content())
                self.assertNotIn('FN-', cells[0].text_content())
                self.assertEqual(cells[0].xpath('.//span[@class="invoice_description_tail"]/text()'), ['Oct 15, 2026 - Nov 14, 2026'])
                self.assertFalse(root.xpath('//div[@name="invoice_unit_list"]'))
                self.assertEqual(len(root.xpath('//div[@class="invoice_signature"]')), 1)
                if quantity == 10:
                    reader = self._pdf(invoice, 'customer-invoice-ten-nopol')
                    self.assertEqual(len(reader.pages), 1)
                    text = ' '.join(reader.pages[0].extract_text().split())
                    for code in plates:
                        self.assertEqual(text.count(code), 1)
                    self.assertNotIn('FN-', text)

    def test_eleven_units_move_to_vertical_list_below_terms_and_keep_posted_data(self):
        _order, invoice, accounts = self._invoice_with_unit_codes(11, posted=True)
        fields = ['name', 'quantity', 'analytic_distribution', 'balance', 'price_subtotal']
        before = invoice.invoice_line_ids.read(fields)
        totals = invoice.read(['state', 'amount_untaxed', 'amount_tax', 'amount_total'])
        root = self._html(invoice)
        cell = root.xpath('//td[@name="account_invoice_line_name"]')[0]
        self.assertNotIn('FN-2026', cell.text_content())
        listing = root.xpath('//div[@name="invoice_unit_list"]')
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0].xpath('./h4/text()'), ['List Nopol'])
        plates = ['B %04d XYZ' % index for index in range(1, 12)]
        self.assertEqual(listing[0].xpath('.//li/span/text()'), plates)
        terms = root.xpath('//div[@name="customer_invoice_terms"]')[0]
        sequence = list(root.iter())
        self.assertLess(sequence.index(terms), sequence.index(listing[0]))
        signature = root.xpath('//div[@class="invoice_signature"]')
        self.assertEqual(len(signature), 1)
        self.assertLess(sequence.index(listing[0]), sequence.index(signature[0]))
        reader = self._pdf(invoice, 'customer-invoice-eleven-nopol')
        self.assertEqual(len(reader.pages), 1)
        text = ' '.join(reader.pages[0].extract_text().split())
        self.assertIn('List Nopol', text)
        for code in plates:
            self.assertEqual(text.count(code), 1)
        self.assertNotIn('FN-', text)
        self.assertEqual(invoice.invoice_line_ids.read(fields), before)
        self.assertEqual(invoice.read(list(totals[0])), totals)

    def test_quantity_threshold_is_per_group_not_invoice_or_stamp_quantity(self):
        _order, invoice, accounts = self._invoice_with_unit_codes(12)
        rentals = invoice.invoice_line_ids.filtered(lambda line: not line.x_is_stamp_duty).sorted('id')
        for line in rentals[6:]:
            line.name = line.name.replace(self.product.name, 'TOYOTA ALL NEW AVANZA (E 1.3 CVT, 2026)')
        groups = invoice._customer_invoice_print_groups(invoice._get_move_lines_to_report())
        self.assertEqual(len(groups), 2)
        self.assertEqual([group['quantity'] for group in groups.values()], [6, 6])
        self.assertTrue(all(not group['show_unit_list'] for group in groups.values()))
        root = self._html(invoice)
        self.assertFalse(root.xpath('//div[@name="invoice_unit_list"]'))
        self.assertEqual(len(root.xpath('//td[@name="account_invoice_line_name"]')), 2)
        for index in range(1, 13):
            self.assertIn('B %04d XYZ' % index, root.xpath('//table[@name="invoice_line_table"]')[0].text_content())

    def test_analytic_snapshot_precedes_changed_sale_line_and_supports_legacy_fallback(self):
        order, invoice, accounts = self._invoice_with_unit_codes(1)
        line = invoice.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty)
        changed_values = {'name': 'FN-CHANGED-SALE-LINE', 'plan_id': self.plan.id, 'company_id': self.company.id}
        if 'license_plate' in accounts._fields:
            changed_values['license_plate'] = 'B 9999 NEW'
        else:
            changed_values['name'] = 'B 9999 NEW'
        changed = self.env['account.analytic.account'].create(changed_values)
        order.order_line.analytic_distribution = {str(changed.id): 100}
        _description, codes = line._customer_invoice_print_unit_details()
        self.assertEqual(codes, ['B 0001 XYZ'])
        line.analytic_distribution = False
        line.x_plate_number = False
        _description, codes = line._customer_invoice_print_unit_details()
        self.assertEqual(codes, ['B 9999 NEW'])

    def test_composite_analytic_keys_exclude_department_when_vehicle_codes_are_available(self):
        _order, invoice, accounts = self._invoice_with_unit_codes(2)
        department_plan = self.env['account.analytic.plan'].create({'name': 'Invoice Department Plan'})
        department = self.env['account.analytic.account'].create({
            'name': 'INTERNAL DEPARTMENT MUST NOT PRINT', 'plan_id': department_plan.id,
            'company_id': self.company.id,
        })
        rentals = invoice.invoice_line_ids.filtered(lambda line: not line.x_is_stamp_duty).sorted('id')
        for line, account in zip(rentals, accounts):
            line.analytic_distribution = {f'{department.id},{account.id}': 100}
        root = self._html(invoice)
        self.assertNotIn(department.name, root.text_content())
        self.assertIn('B 0001 XYZ, B 0002 XYZ', root.text_content())
        self.assertNotIn('FN-2026-', root.text_content())
        accounts[0].active = False
        self.assertIn('B 0001 XYZ', self._html(invoice).text_content())

    def test_fees_do_not_add_unit_codes_and_missing_analytic_is_not_invented(self):
        _order, invoice, _accounts = self._invoice_with_unit_codes(1)
        stamp = invoice.invoice_line_ids.filtered('x_is_stamp_duty')
        stamp.analytic_distribution = {str(self.unit_account.id): 100}
        self.assertEqual(stamp._customer_invoice_print_unit_details()[1], [])
        line = invoice.invoice_line_ids - stamp
        line.analytic_distribution = False
        line.sale_line_ids.analytic_distribution = False
        line.sale_line_ids.fleet_vehicle_id = False
        line.x_plate_number = 'FN-DO-NOT-PRINT'
        line.name = self.product.name + '\nFN-DO-NOT-PRINT\n15-10-2026 - 14-11-2026'
        description, codes = line._customer_invoice_print_unit_details()
        self.assertFalse(codes)
        self.assertNotIn('FN-', description)

    def test_long_unit_list_paginates_without_clipping_and_signature_appears_once(self):
        _order, invoice, accounts = self._invoice_with_unit_codes(65)
        reader = self._pdf(invoice, 'customer-invoice-long-nopol-list')
        self.assertGreater(len(reader.pages), 1)
        text = ' '.join(' '.join(page.extract_text().split()) for page in reader.pages)
        self.assertEqual(text.count('List Nopol'), 1)
        for code in ['B %04d XYZ' % index for index in range(1, 66)]:
            self.assertEqual(text.count(code), 1)
        self.assertNotIn('FN-', text)
        self.assertEqual(text.count('Alvina Jeriwati'), 1)
        self.assertLess(text.index('B 0065 XYZ'), text.index('Alvina Jeriwati'))

    def test_asset_names_are_not_printed_or_rendered_as_html(self):
        _order, invoice, accounts = self._invoice_with_unit_codes(1)
        accounts.name = 'FN-2026-TEST <b>CODE</b> & UNIT'
        root = self._html(invoice)
        cell = root.xpath('//td[@name="account_invoice_line_name"]')[0]
        self.assertNotIn(accounts.name, cell.text_content())
        self.assertIn('B 0001 XYZ', cell.text_content())
        self.assertNotIn('FN-', cell.text_content())
        self.assertFalse(cell.xpath('.//b'))

    def test_nopol_is_resolved_from_invoice_analytic_not_asset_name_or_live_sale(self):
        _order, invoice, accounts = self._invoice_with_unit_codes(1)
        if 'license_plate' not in accounts._fields:
            self.skipTest('Analytic license-plate extension is not installed.')
        line = invoice.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty)
        line.x_plate_number = False
        accounts.license_plate = 'B 8888 ABC'
        root = self._html(invoice)
        cell = root.xpath('//td[@name="account_invoice_line_name"]')[0].text_content()
        self.assertIn('B 8888 ABC', cell)
        self.assertNotIn(accounts.name, cell)
        # A real registration captured on the issued line remains historical.
        line.x_plate_number = 'B 1234 OLD'
        self.assertEqual(line._customer_invoice_print_unit_details()[1], ['B 1234 OLD'])

    def test_multiple_vehicle_analytics_supply_all_nopol_on_one_accounting_line(self):
        _order, invoice, accounts = self._invoice_with_unit_codes(2)
        if 'license_plate' not in accounts._fields:
            self.skipTest('Analytic license-plate extension is not installed.')
        rentals = invoice.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty).sorted('id')
        rentals[0].write({
            'quantity': 2,
            'analytic_distribution': {str(account.id): 50 for account in accounts},
        })
        rentals[1].unlink()
        self.assertEqual(rentals[0]._customer_invoice_print_unit_details()[1], ['B 0001 XYZ', 'B 0002 XYZ'])

    def test_legacy_analytic_name_can_be_a_real_nopol_but_fn_is_not_a_nopol(self):
        _order, invoice, accounts = self._invoice_with_unit_codes(1)
        line = invoice.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty)
        line.x_plate_number = False
        line.sale_line_ids.fleet_vehicle_id = False
        line.sale_line_ids.analytic_distribution = False
        line.name = self.product.name + '\n15-10-2026 - 14-11-2026'
        if 'license_plate' in accounts._fields:
            accounts.license_plate = False
        accounts.name = 'b4321def'
        self.assertEqual(line._customer_invoice_print_unit_details()[1], ['B 4321 DEF'])
        accounts.name = 'FN-NOT-A-REGISTRATION'
        self.assertEqual(line._customer_invoice_print_unit_details()[1], [])

    def test_grouping_different_rates_discounts_and_zero_quantity_keeps_exact_amounts(self):
        _order, invoice = self._invoice(units=2)
        lines = invoice.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty).sorted('id')
        lines[0].write({'quantity': 2, 'price_unit': 1000, 'discount': 10})
        lines[1].write({'quantity': 1, 'price_unit': 2000, 'discount': 25})
        group = next(iter(invoice._customer_invoice_print_groups(lines).values()))
        self.assertEqual(group['quantity'], 3)
        self.assertEqual(group['price_subtotal'], 3300)
        self.assertAlmostEqual(group['quantity'] * group['price_unit'] * (1 - group['discount'] / 100), 3300)
        table = self._html(invoice).xpath('//table[@name="invoice_line_table"]')[0]
        self.assertIn('3,300.00', table.xpath('.//td[@name="td_subtotal"]')[0].text_content())
        lines[1].quantity = -2
        group = next(iter(invoice._customer_invoice_print_groups(lines).values()))
        self.assertEqual(group['quantity'], 0)
        self.assertEqual(group['price_subtotal'], sum(lines.mapped('price_subtotal')))
        self._html(invoice)  # No division by zero during rendering.

    def test_dpp_excludes_legacy_and_other_biaya_only_in_print(self):
        _order, invoice = self._invoice()
        stamp = invoice.invoice_line_ids.filtered('x_is_stamp_duty')
        stamp.x_is_stamp_duty = False  # Old/manual stamp without the system marker.
        invoice.write({'invoice_line_ids': [Command.create({
            'name': 'BIAYA Administrasi', 'quantity': 1, 'price_unit': 25000,
            'account_id': self.income_account.id, 'tax_ids': [Command.clear()],
        })]})
        before = invoice.read(['amount_untaxed', 'amount_tax', 'amount_total', 'invoice_line_ids'])
        self.assertEqual(invoice.amount_untaxed, 9535000)
        self.assertEqual(invoice._customer_invoice_print_dpp(), 9500000)
        self.assertEqual(sum(invoice._customer_invoice_print_fees().mapped('price_subtotal')), 35000)
        root = self._html(invoice)
        dpp = root.xpath('//div[@id="total"]//tr[contains(@class, "o_subtotal")]')[0]
        self.assertIn('9,500,000.00', dpp.text_content())
        table = root.xpath('//table[@name="invoice_line_table"]')[0].text_content()
        self.assertIn('Biaya Materai', table)
        self.assertIn('BIAYA Administrasi', table)
        self.assertEqual(invoice.read(['amount_untaxed', 'amount_tax', 'amount_total', 'invoice_line_ids']), before)

    def test_staging_example_groups_two_units_without_changing_ppn_pph_total(self):
        taxes = self.env['account.tax']
        for name, rate in (('PPN 11%', 11), ('PPh 23', -2)):
            group = self.env['account.tax.group'].create({
                'name': name, 'country_id': self.company.account_fiscal_country_id.id,
            })
            taxes |= self.env['account.tax'].create({
                'name': name, 'amount': rate, 'type_tax_use': 'sale', 'tax_group_id': group.id,
            })
        _order, invoice = self._invoice(units=2, taxes=taxes)
        rentals = invoice.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty)
        rentals.write({
            'name': 'TOYOTA ALL NEW AVANZA (E 1.3 CVT, 2026)\n16th September 2026 - 15th October 2026',
            'price_unit': 5400000,
        })
        invoice.invoice_line_ids.filtered('x_is_stamp_duty').x_is_stamp_duty = False
        before = invoice.read(['amount_untaxed', 'amount_tax', 'amount_total', 'invoice_line_ids'])
        self.assertEqual(invoice.amount_untaxed, 10810000)
        self.assertEqual(invoice.amount_tax, 972000)
        self.assertEqual(invoice.amount_total, 11782000)
        self.assertEqual(invoice._customer_invoice_print_dpp(), 10800000)
        root = self._html(invoice)
        table = root.xpath('//table[@name="invoice_line_table"]')[0]
        self.assertEqual(len(table.xpath('.//td[@name="account_invoice_line_name"]')), 2)
        self.assertEqual(table.xpath('.//td[@name="td_quantity"]')[0].text_content().strip(), '2.00')
        # The native monetary widget inserts a zero-width no-break marker
        # after the minus sign; ignore that typography when checking values.
        totals = root.xpath('//div[@id="total"]')[0].text_content().replace('\ufeff', '')
        for amount in ('10,800,000.00', '1,188,000.00', '-216,000.00', '11,782,000.00'):
            self.assertIn(amount, totals)
        pdf = self._pdf(invoice, 'customer-invoice-staging-example')
        self.assertEqual(len(pdf.pages), 1)
        self.assertEqual(invoice.read(['amount_untaxed', 'amount_tax', 'amount_total', 'invoice_line_ids']), before)

    def test_tax_included_credit_note_uses_summed_total_not_representative_line(self):
        self.company.account_price_include = 'tax_included'
        group = self.env['account.tax.group'].create({
            'name': 'PPN 11%', 'country_id': self.company.account_fiscal_country_id.id,
        })
        ppn = self.env['account.tax'].create({
            'name': 'PPN 11%', 'amount': 11, 'type_tax_use': 'sale', 'tax_group_id': group.id,
        })
        _order, invoice = self._invoice(units=2, taxes=ppn)
        credit = invoice.copy({'move_type': 'out_refund'})
        rental_lines = credit.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty)
        expected = sum(rental_lines.mapped('price_total'))
        table = self._html(credit).xpath('//table[@name="invoice_line_table"]')[0]
        self.assertEqual(len(table.xpath('.//td[@name="account_invoice_line_name"]')), 1)
        self.assertEqual(table.xpath('.//td[@name="td_quantity"]')[0].text_content().strip(), '2.00')
        self.assertIn(f'{expected:,.2f}', table.xpath('.//td[@name="td_subtotal"]')[0].text_content())

    def test_terms_column_is_bounded_and_tax_totals_have_borders(self):
        _order, invoice = self._invoice(units=2)
        invoice.narration = '<p>Terms and Payment:</p><ul>%s</ul>' % ''.join(
            '<li>%s</li>' % clause for clause in (
                'Denda keterlambatan sebesar 0,2% dari harga sewa yang tertunda, dihitung sejak tanggal jatuh tempo sampai dengan tanggal pembayaran.',
                'Pembayaran dianggap sah apabila telah diterima di rekening PT. Cakrawala Rentalindo Sejahtera.',
                'Silahkan melakukan konfirmasi pembayaran melalui email finance@cakrawalarentalindo.com.',
                'Apabila terdapat kesalahan pada invoice yang sudah diterima kami tidak bisa membatalkan invoice tersebut dan hanya bisa merevisi untuk periode berikutnya.',
                'PPH 23 dipotong dengan tarif 2% dari nilai invoice (tidak termasuk PPN), bukti pemotongan PPH 23 agar dikirim melalui email finance@cakrawalarentalindo.com.',
            )
        )
        root = self._html(invoice)
        self.assertEqual(len(root.xpath('//div[@name="customer_invoice_terms"]//li')), 5)
        style = '\n'.join(root.xpath('//style/text()'))
        self.assertIn('.o_total_table td { border: 1px solid #777 !important;', style)
        self.assertIn('.invoice_payment { width: 58%; max-width: 58%;', style)
        pdf = self._pdf(invoice, 'customer-invoice-five-terms')
        self.assertEqual(len(pdf.pages), 1)
        text = ' '.join(pdf.pages[0].extract_text().split())
        self.assertIn('Denda keterlambatan sebesar 0,2%', text)
        self.assertIn('hanya bisa merevisi untuk periode berikutnya.', text)

    @skipUnless(shutil.which('pdftoppm'), 'PDF border checks require Poppler')
    def test_staging_totals_border_keeps_posted_accounting_unchanged(self):
        taxes = self.env['account.tax']
        for name, rate in (('PPN (11%)', 11), ('PPh 23 (2%)', -2)):
            group = self.env['account.tax.group'].create({
                'name': name, 'country_id': self.company.account_fiscal_country_id.id,
            })
            taxes |= self.env['account.tax'].create({
                'name': name, 'amount': rate, 'type_tax_use': 'sale', 'tax_group_id': group.id,
            })
        _order, invoice = self._invoice(units=2, taxes=taxes)
        invoice.invoice_line_ids.filtered('x_is_stamp_duty').unlink()
        invoice.invoice_line_ids.price_unit = 25800000
        invoice.action_post()
        before = invoice.read(['state', 'amount_untaxed', 'amount_tax', 'amount_total', 'invoice_line_ids'])
        self.assertEqual(invoice.amount_untaxed, 51600000)
        self.assertEqual(invoice.amount_total, 56244000)
        table = self._html(invoice).xpath('//div[@id="total"]//table')[0]
        self.assertIn('o_ignore_layout_styling', table.get('class').split())
        reader = self._pdf(invoice, 'customer-invoice-border')
        self.assertEqual(len(reader.pages), 1)
        text = ' '.join(reader.pages[0].extract_text().split())
        for value in ('51,600,000.00', '5,676,000.00', '1,032,000.00', '56,244,000.00'):
            self.assertIn(value, text)
        self._assert_totals_pdf_outline(reader)
        self.assertEqual(invoice.read(list(before[0])), before)

    def test_vendor_totals_keep_native_table_styling(self):
        payable = self.env['account.account'].create({
            'name': 'Invoice Layout Test Payable', 'code': '799990103',
            'account_type': 'liability_payable', 'reconcile': True,
            'company_ids': [Command.set(self.company.ids)],
        })
        self.partner.property_account_payable_id = payable
        journal = self.env['account.journal'].create({
            'name': 'Invoice Layout Test Purchases', 'code': 'LAYP',
            'type': 'purchase', 'company_id': self.company.id,
        })
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.partner.id,
            'journal_id': journal.id, 'invoice_date': date(2026, 10, 15),
            'invoice_line_ids': [Command.create({
                'product_id': self.product.id, 'account_id': self.income_account.id,
                'quantity': 1, 'price_unit': 100000, 'tax_ids': [Command.clear()],
            })],
        })
        root = self._html(bill)
        table = root.xpath('//div[@id="total"]//table')[0]
        self.assertNotIn('o_ignore_layout_styling', table.get('class').split())
        self.assertFalse(root.xpath('//div[contains(@class,"o_cakrawala_invoice")]'))

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

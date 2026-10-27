from datetime import date

from lxml import html

from odoo import Command
from odoo.tests import tagged

from .test_invoice_report import CakrawalaInvoiceReportCommon


@tagged('post_install', '-at_install')
class TestRentalInvoiceDetail(CakrawalaInvoiceReportCommon):

    def _tax(self, name, amount, **extra):
        group = self.env['account.tax.group'].create({
            'name': name, 'country_id': self.company.account_fiscal_country_id.id,
        })
        return self.env['account.tax'].create({
            'name': name, 'amount': amount, 'type_tax_use': 'sale',
            'tax_group_id': group.id, **extra,
        })

    def _ppn_pph(self):
        return self._tax('PPN 11%', 11) | self._tax('PPh 23 (2%)', -2)

    def _product_rows(self, details):
        return [row for row in details['rows'] if row['display_type'] == 'product']

    def _assert_reconciles(self, invoice, details):
        rows = self._product_rows(details)
        for row in rows:
            self.assertAlmostEqual(row['total'], row['subtotal'] + row['ppn'] - row['pph'] + row['other_tax'], places=2)
        for field in ['subtotal', 'ppn', 'pph', 'other_tax', 'total']:
            self.assertAlmostEqual(sum(row[field] for row in rows), details['totals'][field], places=2)
        self.assertAlmostEqual(details['totals']['total'], invoice.amount_total, places=2)
        self.assertAlmostEqual(details['totals']['ppn'] - details['totals']['pph'] + details['totals']['other_tax'], invoice.amount_tax, places=2)

    def test_single_unit_uses_actual_ungrouped_invoice_lines_and_billing_months(self):
        order, invoice = self._invoice(taxes=self._ppn_pph())
        first = invoice.invoice_line_ids.filtered(lambda line: not line.x_is_stamp_duty)
        first.x_billing_month = '1 of 36'
        second = first.copy({'move_id': invoice.id, 'x_billing_month': '2 of 36', 'sequence': first.sequence + 1})
        second.name = second.name.replace('15-10-2026 - 14-11-2026', '15-11-2026 - 14-12-2026')
        data = invoice._rental_invoice_print_details()
        self.assertTrue(data['single_unit'])
        self.assertEqual(data['unit_quantity'], 1)
        rentals = [row for row in self._product_rows(data) if not row['is_fee']]
        self.assertEqual([row['line_id'] for row in rentals], (first | second).ids)
        self.assertEqual([row['billing_month'] for row in rentals], ['1 of 36', '2 of 36'])
        root = self._html(invoice)
        self.assertFalse(root.xpath('//table[@name="invoice_line_table"]'))
        self.assertFalse(root.xpath('//div[@name="rental_invoice_appendix"]'))
        table = root.xpath('//table[@name="rental_invoice_detail_table"]')[0]
        self.assertEqual(len(table.xpath('.//tr[@class="rental_detail_row"]')), 2)
        self.assertIn('2 of 36', table.text_content())
        self._assert_reconciles(invoice, data)

    def test_single_unit_annual_quantity_is_not_twelve_vehicles(self):
        _order, invoice = self._invoice()
        line = invoice.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty)
        line.write({'quantity': 12, 'x_billing_month': '1-12 of 36'})
        data = invoice._rental_invoice_print_details()
        self.assertTrue(data['single_unit'])
        self.assertEqual(data['unit_quantity'], 1)
        self.assertFalse(self._html(invoice).xpath('//div[@name="rental_invoice_appendix"]'))
        self._assert_reconciles(invoice, data)

    def test_multi_unit_summary_and_next_page_appendix_only_current_invoice(self):
        _order, invoice, _accounts = self._invoice_with_unit_codes(3)
        rentals = invoice.invoice_line_ids.filtered(lambda item: not item.x_is_stamp_duty).sorted('id')
        rentals[1:].unlink()  # Contract still has 3 units, invoice charges only one.
        data = invoice._rental_invoice_print_details()
        self.assertFalse(data['single_unit'])
        self.assertEqual(data['unit_quantity'], 3)
        self.assertEqual([row['line_id'] for row in self._product_rows(data) if not row['is_fee']], rentals[:1].ids)
        root = self._html(invoice)
        self.assertTrue(root.xpath('//table[@name="invoice_line_table"]'))
        appendix = root.xpath('//div[@name="rental_invoice_appendix"]')[0]
        self.assertIn('B 0001 XYZ', appendix.text_content())
        self.assertNotIn('B 0002 XYZ', root.text_content())
        self.assertNotIn('B 0003 XYZ', root.text_content())

    def test_input_order_quantity_selects_layout_but_never_overrides_invoice_prices(self):
        order, invoice = self._invoice()
        order.input_line_ids = [Command.create({
            'product_id': self.product.id, 'name': self.product.name,
            'quantity': 2, 'price_unit': 1, 'tax_ids': [Command.clear()],
        })]
        data = invoice._rental_invoice_print_details()
        self.assertEqual(data['unit_quantity'], 2)
        self.assertFalse(data['single_unit'])
        rentals = [row for row in self._product_rows(data) if not row['is_fee']]
        self.assertEqual(rentals[0]['subtotal'], 9500000)
        self._assert_reconciles(invoice, data)

    def test_staging_twelve_units_nominal_taxes_stamp_and_pdf_page_break(self):
        _order, invoice, _accounts = self._invoice_with_unit_codes(12)
        rentals = invoice.invoice_line_ids.filtered(lambda line: not line.x_is_stamp_duty)
        rentals.write({'price_unit': 4300000, 'tax_ids': [Command.set(self._ppn_pph().ids)],
                       'x_billing_month': '1 of 36'})
        invoice.action_post()
        before = invoice.read(['state', 'name', 'amount_untaxed', 'amount_tax', 'amount_total', 'invoice_line_ids'])
        line_fields = ['name', 'quantity', 'price_unit', 'discount', 'tax_ids', 'balance', 'analytic_distribution']
        before_lines = invoice.line_ids.read(line_fields)
        data = invoice._rental_invoice_print_details()
        self.assertEqual(data['totals'], {
            'subtotal': 51610000, 'ppn': 5676000, 'pph': 1032000, 'other_tax': 0, 'total': 56254000,
        })
        self.assertEqual(invoice._customer_invoice_print_dpp(), 51600000)
        self._assert_reconciles(invoice, data)
        root = self._html(invoice)
        appendix = root.xpath('//div[@name="rental_invoice_appendix"]')[0]
        self.assertEqual(len(appendix.xpath('.//tr[@class="rental_detail_row"]')), 12)
        self.assertEqual(len(appendix.xpath('.//tr[@class="rental_detail_fee"]')), 1)
        self.assertFalse(root.xpath('//div[@name="invoice_unit_list"]'))
        self.assertNotIn('B 0001 XYZ', root.xpath('//table[@name="invoice_line_table"]')[0].text_content())
        reader = self._pdf(invoice, 'rental-invoice-twelve-unit-appendix')
        self.assertEqual(len(reader.pages), 2)
        first, second = [' '.join(page.extract_text().split()) for page in reader.pages]
        self.assertIn('Alvina Jeriwati', first)
        self.assertNotIn('LAMPIRAN RINCIAN INVOICE', first)
        self.assertIn('LAMPIRAN RINCIAN INVOICE', second)
        self.assertIn('B 0012 XYZ', second)
        for value in ['51,610,000.00', '5,676,000.00', '1,032,000.00', '56,254,000.00']:
            self.assertIn(value, second)
        self.assertEqual(invoice.read(list(before[0])), before)
        self.assertEqual(invoice.line_ids.read(line_fields), before_lines)

    def test_single_unit_pdf_has_nominal_tax_columns_and_reconciled_total(self):
        _order, invoice = self._invoice(taxes=self._ppn_pph(), posted=True)
        reader = self._pdf(invoice, 'rental-invoice-single-unit-detail')
        self.assertEqual(len(reader.pages), 1)
        text = ' '.join(reader.pages[0].extract_text().split())
        for expected in ['No Polisi', 'Bulan Ke', 'PPN', 'PPh', '9,500,000.00',
                         '1,045,000.00', '190,000.00', '10,365,000.00', 'Biaya Materai']:
            self.assertIn(expected, text)
        self.assertNotIn('LAMPIRAN RINCIAN INVOICE', text)

    def test_different_rates_discounts_and_products_are_not_grouped_in_details(self):
        _order, invoice = self._invoice(units=2, taxes=self._ppn_pph())
        rentals = invoice.invoice_line_ids.filtered(lambda line: not line.x_is_stamp_duty).sorted('id')
        rentals[0].write({'price_unit': 10000000, 'discount': 10, 'x_billing_month': '1 of 36'})
        rentals[1].write({'price_unit': 7000000, 'discount': 5, 'x_billing_month': '2 of 36',
                          'name': 'TOYOTA CAMRY\nB 9999 XYZ\n15-10-2026 - 14-11-2026'})
        data = invoice._rental_invoice_print_details()
        values = [row for row in self._product_rows(data) if not row['is_fee']]
        self.assertEqual(len(values), 2)
        self.assertEqual([row['subtotal'] for row in values], [9000000, 6650000])
        self.assertEqual([row['ppn'] for row in values], [990000, 731500])
        self.assertEqual([row['pph'] for row in values], [180000, 133000])
        self._assert_reconciles(invoice, data)

    def test_group_tax_uses_child_ppn_and_pph_amounts(self):
        children = self._ppn_pph()
        group = self._tax('Rental Combined Tax', 0, amount_type='group', children_tax_ids=[Command.set(children.ids)])
        _order, invoice = self._invoice(taxes=group)
        data = invoice._rental_invoice_print_details()
        self.assertEqual(data['totals']['ppn'], 1045000)
        self.assertEqual(data['totals']['pph'], 190000)
        self.assertFalse(data['show_other_tax'])
        self._assert_reconciles(invoice, data)

    def test_tax_included_price_and_credit_note_keep_native_tax_amounts(self):
        tax = self._tax('PPN 11%', 11, price_include_override='tax_included')
        _order, invoice = self._invoice(taxes=tax)
        invoice.invoice_line_ids.filtered(lambda line: not line.x_is_stamp_duty).price_unit = 10545000
        invoice.action_post()
        for move in [invoice, invoice.copy({'move_type': 'out_refund'})]:
            data = move._rental_invoice_print_details()
            self.assertEqual(data['totals']['ppn'], 1045000)
            self.assertEqual(data['totals']['subtotal'], 9510000)
            self.assertEqual(data['totals']['total'], 10555000)
            self._assert_reconciles(move, data)

    def test_global_rounding_allocates_native_tax_amounts_without_per_line_recalculation(self):
        self.company.tax_calculation_rounding_method = 'round_globally'
        taxes = self._ppn_pph()
        _order, invoice = self._invoice(units=3, taxes=taxes)
        invoice.invoice_line_ids.filtered('x_is_stamp_duty').unlink()
        invoice.invoice_line_ids.price_unit = 0.05
        data = invoice._rental_invoice_print_details()
        self._assert_reconciles(invoice, data)
        self.assertEqual(data['totals']['ppn'], 0.02)  # Not 0.01 * 3.
        self.assertFalse(any(row['description'].startswith('Penyesuaian') for row in self._product_rows(data)))

    def test_manual_tax_amount_is_preserved_from_actual_tax_journal_lines(self):
        _order, invoice = self._invoice(taxes=self._ppn_pph())
        tax_line = invoice.line_ids.filtered(lambda line: line.tax_line_id.amount > 0)
        # Customer tax journal lines are credits (negative amount_currency).
        tax_line.amount_currency += 123
        before = invoice.line_ids.read(['amount_currency', 'balance'])
        data = invoice._rental_invoice_print_details()
        self.assertEqual(data['totals']['ppn'], 1044877)
        self._assert_reconciles(invoice, data)
        self.assertEqual(invoice.line_ids.read(['amount_currency', 'balance']), before)

    def test_other_tax_is_disclosed_and_not_mislabeled_as_ppn(self):
        taxes = self._ppn_pph() | self._tax('Other Service Tax', 1)
        _order, invoice = self._invoice(taxes=taxes)
        data = invoice._rental_invoice_print_details()
        self.assertTrue(data['show_other_tax'])
        self.assertEqual(data['totals']['other_tax'], 95000)
        self.assertIn('Pajak Lain', self._html(invoice).text_content())
        self._assert_reconciles(invoice, data)

    def test_stamp_other_biaya_and_taxed_fees_are_separate_rows_dpp_stays_exclusive(self):
        ppn = self._tax('PPN', 11)
        _order, invoice = self._invoice(taxes=ppn)
        invoice.invoice_line_ids = [Command.create({
            'name': 'BIAYA ADMINISTRASI', 'account_id': self.income_account.id,
            'quantity': 1, 'price_unit': 50000, 'tax_ids': [Command.set(ppn.ids)],
        })]
        data = invoice._rental_invoice_print_details()
        fees = [row for row in self._product_rows(data) if row['is_fee']]
        self.assertCountEqual([row['description'] for row in fees], ['Biaya Materai', 'BIAYA ADMINISTRASI'])
        self.assertEqual(invoice._customer_invoice_print_dpp(), 9500000)
        self._assert_reconciles(invoice, data)

    def test_sections_notes_original_order_and_html_escaping_are_preserved(self):
        _order, invoice = self._invoice()
        rental = invoice.invoice_line_ids.filtered(lambda line: not line.x_is_stamp_duty)
        rental.sequence = 20
        invoice.invoice_line_ids = [
            Command.create({'display_type': 'line_section', 'name': 'SEWA <script>unsafe</script>', 'sequence': 10}),
            Command.create({'display_type': 'line_note', 'name': 'Catatan <b>literal</b>', 'sequence': 30}),
        ]
        root = self._html(invoice)
        detail = root.xpath('//table[@name="rental_invoice_detail_table"]')[0]
        notes = detail.xpath('.//tr[@class="rental_detail_note"]')
        self.assertEqual(len(notes), 2)
        self.assertIn('<script>unsafe</script>', notes[0].text_content())
        self.assertFalse(detail.xpath('.//script | .//b'))

    def test_unlinked_legacy_rental_invoice_falls_back_to_invoice_units_not_fees(self):
        _order, invoice = self._invoice(units=2)
        invoice.invoice_line_ids.sale_line_ids = [Command.clear()]
        self.assertFalse(invoice.invoice_line_ids.sale_line_ids)
        data = invoice._rental_invoice_print_details()
        self.assertEqual(data['unit_quantity'], 2)
        self.assertFalse(data['single_unit'])
        self._assert_reconciles(invoice, data)

    def test_ordinary_customer_invoice_and_et_penalty_keep_previous_layout(self):
        _order, invoice = self._invoice()
        invoice.invoice_line_ids.sale_line_ids = [Command.clear()]
        invoice.x_is_rental_invoice = False
        self.assertFalse(invoice._rental_invoice_print_details())
        self.assertTrue(self._html(invoice).xpath('//table[@name="invoice_line_table"]'))
        self.assertFalse(self._html(invoice).xpath('//table[@name="rental_invoice_detail_table"]'))
        invoice.write({'x_is_rental_invoice': True, 'is_et_penalty_invoice': True})
        self.assertFalse(invoice._rental_invoice_print_details())

    def test_invoice_without_payments_report_and_batch_output_include_appendix(self):
        _order, single = self._invoice()
        _order, multi = self._invoice(units=2)
        content, _kind = self.env['ir.actions.report']._render_qweb_html(
            'account.report_invoice_with_payments', single.ids + multi.ids,
        )
        root = html.fromstring(content)
        self.assertEqual(len(root.xpath('//table[@name="rental_invoice_detail_table"]')), 2)
        self.assertEqual(len(root.xpath('//div[@name="rental_invoice_appendix"]')), 1)
        reader = self._pdf(single | multi, 'rental-invoice-batch')
        self.assertEqual(len(reader.pages), 3)
        self.assertEqual(sum('LAMPIRAN RINCIAN INVOICE' in page.extract_text() for page in reader.pages), 1)

    def test_cash_rounding_is_disclosed_and_reconciles_without_changing_any_line(self):
        expense = self.env['account.account'].create({
            'name': 'Detail Rounding Expense', 'code': '799990199',
            'account_type': 'expense', 'company_ids': [Command.set(self.company.ids)],
        })
        rounding = self.env['account.cash.rounding'].create({
            'name': 'Detail 0.05 Rounding', 'rounding': 0.05,
            'strategy': 'add_invoice_line', 'rounding_method': 'HALF-UP',
            'profit_account_id': self.income_account.id, 'loss_account_id': expense.id,
        })
        _order, invoice = self._invoice()
        invoice.invoice_line_ids.filtered('x_is_stamp_duty').unlink()
        invoice.invoice_line_ids.price_unit = 0.12
        invoice.invoice_cash_rounding_id = rounding
        before = invoice.line_ids.read(['name', 'display_type', 'amount_currency', 'balance'])
        data = invoice._rental_invoice_print_details()
        self.assertAlmostEqual(data['totals']['total'], 0.10, places=2)
        self._assert_reconciles(invoice, data)
        self.assertTrue(any(row['line_id'] is False for row in self._product_rows(data)))
        self.assertEqual(invoice.line_ids.read(['name', 'display_type', 'amount_currency', 'balance']), before)

    def test_zero_quantity_and_negative_adjustments_keep_exact_invoice_values(self):
        _order, invoice = self._invoice(taxes=self._ppn_pph())
        invoice.invoice_line_ids = [Command.create({
            'name': 'Biaya adjustment', 'quantity': -1, 'price_unit': 12345.67,
            'account_id': self.income_account.id, 'tax_ids': [Command.clear()],
        }), Command.create({
            'name': 'Zero quantity information', 'quantity': 0, 'price_unit': 99999,
            'account_id': self.income_account.id, 'tax_ids': [Command.clear()],
        })]
        data = invoice._rental_invoice_print_details()
        self.assertTrue(data['single_unit'])
        self._assert_reconciles(invoice, data)
        self._html(invoice)

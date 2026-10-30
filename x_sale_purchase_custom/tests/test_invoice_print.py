from unittest.mock import patch

from lxml import html

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.addons.base.models.ir_actions_report import IrActionsReport as BaseReport

from ..models.invoice_print import PRINT_SNAPSHOT
from .test_invoice_report import CakrawalaInvoiceReportCommon
from .test_invoice_report_separation import TestInvoiceReportSeparation


REPORT = 'x_sale_purchase_custom.action_report_invoice_custom'


@tagged('post_install', '-at_install')
class TestCustomInvoicePrint(CakrawalaInvoiceReportCommon):
    _snapshot = TestInvoiceReportSeparation._snapshot

    def _count(self, invoice):
        return self.env['rental.invoice.print.log'].sudo().search([('move_id', '=', invoice.id)]).print_count or 0

    def _fake_pdf(self, invoices, reports=None, data=None):
        seen = []

        def render(renderer, report_ref, res_ids=None, data=None):
            seen.append(renderer.env.context.get(PRINT_SNAPSHOT, []))
            return b'%PDF-test', 'pdf'

        with patch.object(BaseReport, '_render_qweb_pdf', render):
            renderer = reports if reports is not None else self.env['ir.actions.report']
            renderer._render_qweb_pdf(REPORT, res_ids=invoices.ids, data=data)
        return seen[0]

    def test_preview_does_not_count_and_pdf_reprint_is_persistent(self):
        _order, invoice = self._invoice(posted=True)
        before = self._snapshot(invoice)
        for _ in range(2):
            self.assertFalse(self._html(invoice).xpath('//*[@name="custom_invoice_reprint"]'))
        self.assertEqual(self._count(invoice), 0)
        self.assertEqual(self._fake_pdf(invoice), [])
        self.assertEqual(self._count(invoice), 1)
        self.assertTrue(self._html(invoice).xpath('//*[@name="custom_invoice_reprint"]'))
        self.assertEqual(self._count(invoice), 1)
        self.env.invalidate_all()
        self.assertEqual(self._fake_pdf(invoice), invoice.ids)
        self.assertEqual(self._count(invoice), 2)
        self.assertEqual(self._snapshot(invoice), before)

    def test_batch_marks_only_previously_printed_invoice_once_per_request(self):
        _order, old = self._invoice()
        _order, new = self._invoice()
        self._fake_pdf(old)
        self.assertEqual(self._fake_pdf(old | new), old.ids)
        self.assertEqual((self._count(old), self._count(new)), (2, 1))
        reports = self.env['ir.actions.report']
        with patch.object(BaseReport, '_render_qweb_pdf', return_value=(b'%PDF-test', 'pdf')):
            reports._render_qweb_pdf(REPORT, res_ids=[new.id, new.id])
            reports._render_qweb_pdf(REPORT, res_ids=old.id)
        self.assertEqual((self._count(old), self._count(new)), (3, 2))

    def test_failed_render_rolls_back_tracking_including_existing_counts(self):
        _order, original = self._invoice()
        _order, reprint = self._invoice()
        self._fake_pdf(reprint)
        for invoice in [original, reprint]:
            before = self._count(invoice)
            with self.assertRaises(UserError), patch.object(BaseReport, '_render_qweb_pdf', side_effect=UserError('PDF rendering failed')):
                self.env['ir.actions.report']._render_qweb_pdf(REPORT, res_ids=invoice.ids)
            self.assertEqual(self._count(invoice), before)
        self.assertFalse(self.env['rental.invoice.print.log'].search([('move_id', '=', original.id)]))

    def test_non_pdf_fallback_does_not_increment(self):
        _order, invoice = self._invoice()
        with patch.object(BaseReport, '_render_qweb_pdf', return_value=(b'<html/>', 'html')):
            self.env['ir.actions.report']._render_qweb_pdf(REPORT, res_ids=invoice.ids)
        self.assertEqual(self._count(invoice), 0)
        self.assertEqual(self._fake_pdf(invoice), [])

    def test_client_data_or_context_cannot_suppress_pdf_reprint(self):
        _order, invoice = self._invoice()
        self._fake_pdf(invoice)
        reports = self.env['ir.actions.report'].with_context(**{PRINT_SNAPSHOT: []})
        self.assertEqual(self._fake_pdf(invoice, reports, {'custom_invoice_reprint_ids': []}), invoice.ids)

    def test_native_report_does_not_increment_or_gain_custom_label(self):
        _order, invoice = self._invoice(posted=True)
        self._fake_pdf(invoice)
        before = self._html(invoice, 'account.report_invoice').text_content()
        with patch.object(BaseReport, '_render_qweb_pdf', return_value=(b'%PDF-test', 'pdf')):
            self.env['ir.actions.report']._render_qweb_pdf('account.account_invoices', res_ids=invoice.ids)
        self.assertEqual(self._count(invoice), 1)
        native = self._html(invoice, 'account.report_invoice')
        self.assertEqual(native.text_content(), before)
        self.assertFalse(native.xpath('//*[@name="custom_invoice_reprint"]'))
        self.assertTrue(native.xpath('//div[@name="delivery_date"]'))

    def test_readonly_accounting_can_print_but_cannot_reset_tracking(self):
        _order, invoice = self._invoice()
        user = new_test_user(self.env, login='custom_pdf_reader', groups='account.group_account_readonly', company_id=self.company.id)
        reports = self.env['ir.actions.report'].with_user(user)
        self.assertFalse(invoice.with_user(user).has_access('write'))
        self.assertEqual(self._fake_pdf(invoice, reports), [])
        self.assertEqual(self._fake_pdf(invoice, reports), invoice.ids)
        log = self.env['rental.invoice.print.log'].search([('move_id', '=', invoice.id)]).with_user(user)
        self.assertEqual(log.print_count, 2)
        for operation in [lambda: log.write({'print_count': 0}), lambda: log.unlink(),
                          lambda: log.create({'move_id': invoice.id, 'print_count': 0})]:
            with self.assertRaises(AccessError):
                operation()

    def test_inaccessible_invoice_does_not_create_tracking(self):
        _order, invoice = self._invoice()
        user = new_test_user(self.env, login='custom_pdf_denied', groups='account.group_account_readonly', company_id=self.company.id)
        self.env['ir.rule'].create({
            'name': 'Deny fixture invoice printing', 'model_id': self.env['ir.model']._get_id('account.move'),
            'domain_force': "[('id', '!=', %d)]" % invoice.id,
        })
        with self.assertRaises(AccessError):
            self._fake_pdf(invoice, self.env['ir.actions.report'].with_user(user))
        self.assertEqual(self._count(invoice), 0)

    def test_copy_has_its_own_first_print_and_credit_notes_are_tracked(self):
        _order, invoice = self._invoice()
        self._fake_pdf(invoice)
        copy = invoice.copy()
        self.assertEqual(self._fake_pdf(copy), [])
        credit = invoice.copy({'move_type': 'out_refund'})
        self.assertEqual(self._fake_pdf(credit), [])
        self.assertEqual(self._fake_pdf(credit), credit.ids)
        self.assertEqual(self._count(invoice), 1)

    def test_actual_single_unit_original_and_reprint_keep_one_page(self):
        _order, invoice = self._invoice(legacy=True, posted=True)
        before = self._snapshot(invoice)
        written_at = invoice.write_date
        first = self._pdf(invoice, 'invoice-first-print')
        second = self._pdf(invoice, 'invoice-reprint')
        for pdf in [first, second]:
            self.assertEqual(len(pdf.pages), 1)
            text = pdf.pages[0].extract_text()
            for forbidden in ['Delivery Date', 'PPN dan PPh dalam nominal', 'RPC/2026']:
                self.assertNotIn(forbidden, text)
        self.assertNotIn('REPRINT', first.pages[0].extract_text())
        self.assertIn('REPRINT', second.pages[0].extract_text())
        self.assertEqual(' '.join(first.pages[0].extract_text().split()),
                         ' '.join(second.pages[0].extract_text().replace('REPRINT', '').split()))
        self.assertEqual(self._count(invoice), 2)
        self.assertEqual(self._snapshot(invoice), before)
        self.assertEqual(invoice.write_date, written_at)

    def test_actual_multi_unit_original_and_reprint_keep_two_pages(self):
        _order, invoice, _accounts = self._invoice_with_unit_codes(12, posted=True)
        before = self._snapshot(invoice)
        written_at = invoice.write_date
        first = self._pdf(invoice, 'invoice-multi-first-print')
        second = self._pdf(invoice, 'invoice-multi-reprint')
        for pdf in [first, second]:
            self.assertEqual(len(pdf.pages), 2)
            self.assertNotIn('Delivery Date', pdf.pages[0].extract_text())
            self.assertNotIn('PPN dan PPh dalam nominal', pdf.pages[1].extract_text())
            self.assertIn('LAMPIRAN RINCIAN INVOICE', pdf.pages[1].extract_text())
        self.assertNotIn('REPRINT', ''.join(page.extract_text() for page in first.pages))
        self.assertTrue(all('REPRINT' in page.extract_text() for page in second.pages))
        for original, reprint in zip(first.pages, second.pages):
            self.assertEqual(' '.join(original.extract_text().split()),
                             ' '.join(reprint.extract_text().replace('REPRINT', '').split()))
        self.assertEqual(self._snapshot(invoice), before)
        self.assertEqual(invoice.write_date, written_at)


@tagged('post_install', '-at_install')
class TestRentalOrderPrintDescription(CakrawalaInvoiceReportCommon):
    def _order_html(self, order):
        content, _ = self.env['ir.actions.report']._render_qweb_html('sale.action_report_saleorder', order.ids)
        return html.fromstring(content)

    def test_input_description_without_rpc_and_transaction_preserved(self):
        order, invoice = self._invoice(units=2)
        source = self.env['sale.order.input.line'].create({
            'order_id': order.id, 'product_id': self.product.id,
            'name': 'RPC/2026/10-00038 - ' + self.product.name + '\nUser delivery note',
            'quantity': 2, 'price_unit': 9500000, 'tax_ids': [Command.clear()],
        })
        before = (source.name, order.order_line.mapped('name'), order.amount_total, invoice.amount_total)
        root = self._order_html(order)
        table = root.xpath('//table[contains(@class,"o_cakrawala_input_order_table")]')[0]
        self.assertNotIn('RPC/2026', table.text_content())
        self.assertIn(self.product.name, table.text_content())
        self.assertIn('User delivery note', table.text_content())
        pdf = self._pdf(order, 'rental-order-no-rpc', report='sale.action_report_saleorder')
        self.assertEqual(len(pdf.pages), 1)
        self.assertNotIn('RPC/2026', ''.join(page.extract_text() for page in pdf.pages))
        self.assertEqual((source.name, order.order_line.mapped('name'), order.amount_total, invoice.amount_total), before)

    def test_order_lines_fallback_without_rpc_but_regular_sales_unchanged(self):
        order, _invoice = self._invoice()
        before = order.order_line.mapped('name')
        self.assertFalse(order.input_line_ids)
        root = self._order_html(order)
        self.assertNotIn('RPC/2026', root.xpath('//table[contains(@class,"o_main_table")]')[0].text_content())
        self.assertEqual(order.order_line.mapped('name'), before)
        order.is_rental_order = False
        self.assertIn('RPC/2026', self._order_html(order).text_content())

import importlib.util

from lxml import etree

from odoo.tests import tagged
from odoo.tools import file_path

from .test_invoice_report import CakrawalaInvoiceReportCommon


@tagged('post_install', '-at_install')
class TestInvoiceReportSeparation(CakrawalaInvoiceReportCommon):
    def _snapshot(self, invoice):
        return (
            invoice.read(['name', 'state', 'partner_id', 'invoice_origin', 'narration',
                          'amount_untaxed', 'amount_tax', 'amount_total', 'amount_residual', 'payment_state'])[0],
            invoice.line_ids.read(['name', 'quantity', 'price_unit', 'discount', 'tax_ids',
                                   'price_subtotal', 'price_total', 'balance', 'analytic_distribution']),
        )

    def _migration(self):
        path = file_path('x_sale_purchase_custom/migrations/19.0.0.52/post-migrate.py')
        spec = importlib.util.spec_from_file_location('split_invoice_report_migration', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, '19.0.0.51')
        self.env.invalidate_all()

    def test_actions_are_separate_and_native_default_is_not_replaced(self):
        _order, invoice = self._invoice()
        custom = self.env.ref('x_sale_purchase_custom.action_report_invoice_custom')
        native = self.env.ref('account.account_invoices')
        without_payments = self.env.ref('account.account_invoices_without_payment')
        self.assertEqual(custom.name, 'Custom Print Out')
        self.assertEqual(custom.report_name, 'x_sale_purchase_custom.report_invoice_custom')
        self.assertEqual(custom.binding_model_id.model, 'account.move')
        self.assertEqual(custom.binding_type, 'report')
        self.assertTrue(custom.is_invoice_report)
        self.assertTrue(invoice._is_action_report_available(custom))
        self.assertEqual(native.report_name, 'account.report_invoice_with_payments')
        self.assertEqual(without_payments.report_name, 'account.report_invoice')
        self.assertEqual(self.env['account.move.send']._get_default_pdf_report_id(invoice), native)
        self.assertNotEqual(native.paperformat_id, custom.paperformat_id)
        self.assertNotEqual(without_payments.paperformat_id, custom.paperformat_id)
        self.assertFalse(custom.attachment_use)
        self.assertFalse(custom.attachment)

    def test_primary_templates_do_not_extend_shared_native_templates(self):
        for xmlid in ['report_invoice_document_signoff', 'external_layout_select_customer_invoice',
                      'report_invoice_compact_margins']:
            view = self.env.ref('x_sale_purchase_custom.' + xmlid)
            self.assertEqual(view.mode, 'primary')
        native = etree.tostring(self.env.ref('account.report_invoice_document')._get_combined_arch()).decode()
        external = etree.tostring(self.env.ref('web.external_layout')._get_combined_arch()).decode()
        wrapper = etree.tostring(self.env.ref('account.report_invoice')._get_combined_arch()).decode()
        for content in [native, external, wrapper]:
            self.assertNotIn('x_sale_purchase_custom.', content)
            self.assertNotIn('cakrawala_customer_invoice', content)
        self.assertIn('web.external_layout', native)

    def test_same_invoice_native_and_custom_html_preserve_all_transactions(self):
        _order, invoice = self._invoice(units=2, legacy=True, posted=True)
        before = self._snapshot(invoice)
        native = self._html(invoice, 'account.report_invoice_with_payments')
        custom = self._html(invoice)
        without_payments = self._html(invoice, 'account.report_invoice')
        for root in [native, without_payments]:
            self.assertFalse(root.xpath('//div[contains(@class,"o_cakrawala_invoice")]'))
            self.assertFalse(root.xpath('//div[@name="rental_invoice_appendix"]'))
            self.assertFalse(root.xpath('//div[@name="customer_invoice_terms"]'))
            self.assertIn('RPC/2026/10-00033', root.text_content())
            self.assertIn('HIDDEN-REFERENCE', root.text_content())
        self.assertTrue(custom.xpath('//div[contains(@class,"o_cakrawala_invoice")]'))
        self.assertTrue(custom.xpath('//div[@name="rental_invoice_appendix"]'))
        self.assertIn('1685656789', custom.text_content())
        self.assertNotIn('RPC/2026/10-00033', custom.text_content())
        self.assertEqual(self._snapshot(invoice), before)

    def test_custom_context_does_not_leak_back_to_standard_or_other_reports(self):
        _order, invoice = self._invoice(units=2)
        before = self._html(invoice, 'account.report_invoice').text_content()
        self._html(invoice)
        native = self._html(invoice.with_context(cakrawala_customer_invoice=True), 'account.report_invoice')
        self.assertEqual(native.text_content(), before)
        self.assertFalse(native.xpath('//div[contains(@class,"o_cakrawala_invoice")]'))

    def test_both_pdfs_keep_same_posted_amounts_but_only_custom_has_appendix(self):
        _order, invoice, _accounts = self._invoice_with_unit_codes(12, posted=True)
        before = self._snapshot(invoice)
        native = self._pdf(invoice, 'invoice-standard-split', report='account.account_invoices')
        custom = self._pdf(invoice, 'invoice-custom-split')
        # Qt can outline the native layout's Lato webfont instead of embedding
        # text. Check native values in its HTML, plus real PDF page/content
        # generation; visual QA covers the native PDF itself.
        native_text = ' '.join(self._html(invoice, 'account.report_invoice_with_payments').text_content().split())
        custom_text = ' '.join(' '.join(page.extract_text().split()) for page in custom.pages)
        self.assertGreater(len(native.pages), 0)
        self.assertGreater(len(native.stream.getvalue()), 10000)
        self.assertNotIn('LAMPIRAN RINCIAN INVOICE', native_text)
        self.assertIn('LAMPIRAN RINCIAN INVOICE', custom_text)
        self.assertEqual(len(custom.pages), 2)
        for text in [native_text, custom_text]:
            self.assertIn('114,010,000.00', text)
        self.assertEqual(self._snapshot(invoice), before)

    def test_native_cached_attachment_is_not_reused_or_overwritten_by_custom(self):
        _order, invoice = self._invoice(units=2, posted=True)
        attachment = self.env['ir.attachment'].create({
            'name': 'existing-standard-invoice.pdf', 'res_model': 'account.move',
            'res_id': invoice.id, 'res_field': 'invoice_pdf_report_file',
            'type': 'binary', 'mimetype': 'application/pdf', 'raw': b'Existing archived invoice PDF',
        })
        self.assertEqual(invoice.invoice_pdf_report_id, attachment)
        before = self._snapshot(invoice)
        pdf = self._pdf(invoice, 'invoice-custom-ignores-standard-cache')
        text = ' '.join(' '.join(page.extract_text().split()) for page in pdf.pages)
        self.assertIn('LAMPIRAN RINCIAN INVOICE', text)
        self.assertEqual(attachment.raw, b'Existing archived invoice PDF')
        self.assertEqual(invoice.invoice_pdf_report_id, attachment)
        self.assertEqual(self._snapshot(invoice), before)

    def test_migration_restores_only_our_old_paperformat_bindings_and_is_idempotent(self):
        custom_format = self.env.ref('x_sale_purchase_custom.paperformat_invoice_custom')
        native = self.env.ref('account.account_invoices')
        without_payments = self.env.ref('account.account_invoices_without_payment')
        native.paperformat_id = custom_format
        without_payments.paperformat_id = custom_format
        self._migration()
        self.assertFalse(native.paperformat_id)
        self.assertFalse(without_payments.paperformat_id)
        other = custom_format.copy({'name': 'Accounting Separate Paperformat'})
        native.paperformat_id = other
        without_payments.paperformat_id = custom_format
        self._migration()
        self.assertEqual(native.paperformat_id, other)
        self.assertFalse(without_payments.paperformat_id)
        self._migration()
        self.assertEqual(native.paperformat_id, other)

    def test_custom_menu_domain_excludes_vendor_bills_and_journal_entries(self):
        _order, invoice = self._invoice()
        custom = self.env.ref('x_sale_purchase_custom.action_report_invoice_custom')
        credit = self.env['account.move'].new({'move_type': 'out_refund'})
        bill = self.env['account.move'].new({'move_type': 'in_invoice'})
        entry = self.env['account.move'].new({'move_type': 'entry'})
        self.assertTrue(credit._is_action_report_available(custom))
        self.assertFalse(bill._is_action_report_available(custom))
        self.assertFalse(entry.filtered_domain([('move_type', 'in', ['out_invoice', 'out_refund'])]))

    def test_actual_upgrade_clears_old_native_paperformat_and_keeps_private_one(self):
        custom = self.env.ref('x_sale_purchase_custom.action_report_invoice_custom')
        self.assertEqual(custom.paperformat_id, self.env.ref('x_sale_purchase_custom.paperformat_invoice_custom'))
        self.assertFalse(self.env.ref('account.account_invoices').paperformat_id)
        self.assertFalse(self.env.ref('account.account_invoices_without_payment').paperformat_id)

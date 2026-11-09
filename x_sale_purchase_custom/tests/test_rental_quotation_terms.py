from lxml import etree, html

from odoo.tests import Form, TransactionCase, tagged

from odoo.addons.x_sale_purchase_custom.models.rental_quotation_terms import (
    RENTAL_QUOTATION_TERMS, SaleOrderRentalQuotationTerms,
)
from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestRentalQuotationTerms(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={
            **cls.env.context, 'tracking_disable': True,
            'mail_create_nosubscribe': True,
        })
        cls.partner, cls.second_partner = cls.env['res.partner'].create([
            {'name': 'Quotation Terms Test Customer'},
            {'name': 'Quotation Terms Second Customer'},
        ])
        cls.env.company.invoice_terms = '<p>Company invoice conditions unchanged</p>'
        cls.env['ir.config_parameter'].sudo().set_param('account.use_invoice_terms', True)

    def _order(self, **values):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id, 'is_rental_order': True, **values,
        })

    def _assert_default_terms(self, value):
        root = html.fromstring(value)
        lists = root.xpath('//ol')
        self.assertEqual([len(node.xpath('./li')) for node in lists], [6, 6, 5])
        expected = html.fromstring(RENTAL_QUOTATION_TERMS)
        self.assertEqual(
            [' '.join(node.text_content().split()) for node in root.xpath('//li')],
            [' '.join(node.text_content().split()) for node in expected.xpath('//li')],
        )
        self.assertEqual(len(root.xpath('//tr/td')), 2)

    def test_new_rental_quotation_has_all_three_sections_and_17_clauses(self):
        order = self._order()
        self._assert_default_terms(order.note)
        self.assertEqual(order.x_terms_conditions, self.env.company.purchase_fleet_terms)
        self.assertEqual(self.env.company.invoice_terms, '<p>Company invoice conditions unchanged</p>')

    def test_form_defaults_and_partner_selection_keep_rental_terms(self):
        model = self.env['sale.order'].with_context(default_is_rental_order=True)
        self._assert_default_terms(model.default_get(['is_rental_order', 'note'])['note'])
        view = self.env['ir.ui.view'].create({
            'name': 'Rental quotation terms onchange test', 'model': 'sale.order',
            'arch': '''<form>
                <field name="partner_id"/>
                <field name="is_rental_order" invisible="1"/>
                <field name="note"/>
            </form>''',
        })
        with Form(model, view=view) as form:
            form.partner_id = self.partner
            self._assert_default_terms(form.note)
            form.note = '<p>User-edited rental quotation terms</p>'
            form.partner_id = self.second_partner
            self.assertIn('User-edited rental quotation terms', form.note)
        self.assertIn('User-edited rental quotation terms', form.record.note)

    def test_api_and_context_explicit_custom_or_empty_note_are_not_replaced(self):
        for note in ('<p>Explicit quotation terms</p>', False):
            with self.subTest(note=note):
                order = self._order(note=note)
                self.assertEqual(order.note, note)
                model = self.env['sale.order'].with_context(
                    default_is_rental_order=True, default_note=note,
                )
                default = model.default_get(['note'])['note']
                if note:
                    self.assertEqual(default, note)
                else:
                    self.assertFalse(default)
                context_order = model.create({'partner_id': self.partner.id})
                self.assertEqual(context_order.note, note)

    def test_non_rental_sales_keep_the_native_company_note(self):
        order = self._order(is_rental_order=False)
        self.assertEqual(order.note, self.env.company.invoice_terms)
        order.partner_id = self.second_partner
        self.assertEqual(order.note, self.env.company.invoice_terms)

    def test_clearing_terms_in_new_form_survives_partner_onchange(self):
        model = self.env['sale.order'].with_context(default_is_rental_order=True)
        view = self.env['ir.ui.view'].create({
            'name': 'Rental empty quotation terms onchange test', 'model': 'sale.order',
            'arch': '''<form>
                <field name="partner_id"/>
                <field name="is_rental_order" invisible="1"/>
                <field name="note"/>
            </form>''',
        })
        with Form(model, view=view) as form:
            form.partner_id = self.partner
            self._assert_default_terms(form.note)
            form.note = False
            form.partner_id = self.second_partner
            self.assertFalse(form.note)
        self.assertFalse(form.record.note)

    def test_existing_terms_and_empty_notes_survive_unrelated_saves_and_partner_changes(self):
        for note in ('<p>Historical agreed terms</p>', False):
            with self.subTest(note=note):
                order = self._order(note=note)
                order.client_order_ref = 'QA customer PO'
                self.assertEqual(order.note, note)
                order.partner_id = self.second_partner
                self.assertEqual(order.note, note)

    def test_api_batch_defaults_do_not_mutate_input_values(self):
        values = [
            {'partner_id': self.partner.id, 'is_rental_order': True},
            {'partner_id': self.partner.id, 'is_rental_order': False},
            {'partner_id': self.partner.id, 'is_rental_order': True, 'note': '<p>Explicit batch note</p>'},
        ]
        before = [dict(value) for value in values]
        orders = self.env['sale.order'].create(values)
        self._assert_default_terms(orders[0].note)
        self.assertEqual(orders[1].note, self.env.company.invoice_terms)
        self.assertEqual(orders[2].note, '<p>Explicit batch note</p>')
        self.assertEqual(values, before)

    def test_quotation_html_uses_the_stored_editable_note(self):
        order = self._order()
        content, _kind = self.env['ir.actions.report']._render_qweb_html('sale.report_saleorder', order.ids)
        root = html.fromstring(content)
        notes = root.xpath('//*[@name="order_note"]')
        self.assertEqual(len(notes), 1)
        self._assert_default_terms(etree.tostring(notes[0], encoding='unicode'))

    def test_invoice_preparation_only_omits_narration_for_new_rentals(self):
        order = self._order()
        self.assertTrue(order.rental_quotation_terms_only)
        native = super(SaleOrderRentalQuotationTerms, order)._prepare_invoice()
        native.pop('narration')
        self.assertEqual(order._prepare_invoice(), native)
        order.note = '<p>Edited quotation-only conditions</p>'
        self.assertNotIn('narration', order._prepare_invoice())
        standard = self._order(is_rental_order=False)
        self.assertFalse(standard.rental_quotation_terms_only)
        self.assertEqual(standard._prepare_invoice()['narration'], standard.note)
        legacy = self._order(note='<p>Historical contract conditions</p>')
        # Simulate the marker's False value on pre-upgrade stored orders.
        legacy.rental_quotation_terms_only = False
        self.assertEqual(legacy._prepare_invoice()['narration'], legacy.note)


@tagged('post_install', '-at_install')
class TestRentalQuotationInvoiceIsolation(RentalBillingEngineInvoiceCommon):
    def test_billing_engine_uses_existing_company_invoice_terms_not_quotation_text(self):
        self.env['ir.config_parameter'].sudo().set_param('account.use_invoice_terms', True)
        self.env.company.invoice_terms = '<p>Existing company invoice conditions</p>'
        order = self._order()
        self.assertIn('Harga diatas sudah termasuk', order.note)
        order.note = '<p>Edited quotation-only coverage clauses</p>'
        invoices = order._generate_billing_engine_invoices()
        self.assertTrue(invoices)
        self.assertEqual(set(invoices.mapped('state')), {'draft'})
        self.assertEqual(set(invoices.mapped('narration')), {'<p>Existing company invoice conditions</p>'})
        self.assertEqual(sum(invoices.mapped('amount_untaxed')), sum(self._rows(order).mapped('amount')))

    def test_empty_invoice_terms_keep_existing_custom_report_fallback(self):
        self.env['ir.config_parameter'].sudo().set_param('account.use_invoice_terms', False)
        self.env.company.invoice_terms = False
        order = self._order()
        invoice = order._generate_billing_engine_invoices()[:1]
        self.assertFalse(invoice.narration)
        before = invoice.read(['narration', 'amount_total', 'state'])
        content, _kind = self.env['ir.actions.report']._render_qweb_html(
            'x_sale_purchase_custom.report_invoice_custom', invoice.ids,
        )
        root = html.fromstring(content)
        terms = root.xpath('//*[@name="customer_invoice_terms"]')[0]
        self.assertIn('Pembayaran dianggap sah', terms.text_content())
        self.assertNotIn('Harga diatas sudah termasuk', terms.text_content())
        self.assertEqual(len(terms.xpath('.//li')), 4)
        self.assertEqual(invoice.read(['narration', 'amount_total', 'state']), before)

    def test_historical_order_and_existing_posted_draft_invoices_are_not_rewritten(self):
        order = self._order(note='<p>Legacy agreed invoice conditions</p>')
        order.rental_quotation_terms_only = False
        invoices = order._generate_billing_engine_invoices()
        self.assertEqual(set(invoices.mapped('narration')), {'<p>Legacy agreed invoice conditions</p>'})
        invoices[:1].action_post()
        before = invoices.read(['narration', 'amount_total', 'state'])
        order.note = '<p>Later quotation edits must not rewrite invoices</p>'
        self.assertFalse(order._generate_billing_engine_invoices())
        order._prepare_invoice()
        self.assertEqual(invoices.read(['narration', 'amount_total', 'state']), before)

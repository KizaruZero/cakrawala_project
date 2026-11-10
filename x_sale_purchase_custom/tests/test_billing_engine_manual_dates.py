from datetime import date

from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged
from odoo.tests.common import new_test_user

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestBillingEngineManualDates(RentalBillingEngineInvoiceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.salesperson = new_test_user(cls.env, login='billing_date_editor',
            groups='sales_team.group_sale_salesman', company_id=cls.company.id)
        cls.other_salesperson = new_test_user(cls.env, login='billing_date_other',
            groups='sales_team.group_sale_salesman', company_id=cls.company.id)

    def _annual(self):
        return self._order(months=36, invoicing_cycle_period='yearly', user_id=self.salesperson.id)

    def _dates(self, row):
        return row.read(['period_start', 'period_end', 'rental_start', 'rental_end',
                         'invoice_date', 'invoice_draft_date'])

    def test_six_dates_editable_and_survive_open_and_invoice_sync(self):
        order = self._annual()
        row = self._rows(order)[0]
        money = row.read(['amount', 'total_days', 'rate_monthly'])
        values = {'period_start': date(2026, 2, 1), 'period_end': date(2026, 12, 30),
            'rental_start': date(2026, 2, 5), 'rental_end': date(2026, 12, 30),
            'invoice_date': date(2026, 2, 7), 'invoice_draft_date': date(2026, 2, 4)}
        row.with_user(self.salesperson).write(values)
        self.assertEqual(set(row.manual_date_fields), set(values))
        self.assertEqual(row.source_period_start, date(2026, 1, 1))
        ids = order.billing_engine_line_ids.ids
        order._sync_billing_engine()
        self.assertEqual(order.billing_engine_line_ids.ids, ids)
        self.assertEqual(self._dates(row)[0], {'id': row.id, **values})
        self.assertEqual(row.read(['amount', 'total_days', 'rate_monthly']), money)
        self.assertEqual(row.period, 'Feb - Dec 2026')
        invoices = order._generate_billing_engine_invoices(batch_months=False)
        self.assertIn(row.invoice_id, invoices)
        self.assertEqual(row.invoice_id.invoice_date, date(2026, 2, 7))
        self.assertEqual(row.invoice_line_id.price_subtotal, row.amount)
        self.assertEqual(self._dates(row)[0], {'id': row.id, **values})

    def test_only_edited_date_is_frozen_other_source_dates_update_normally(self):
        order = self._order(months=1, user_id=self.salesperson.id)
        row = self._rows(order)
        row.with_user(self.salesperson).invoice_date = date(2026, 1, 25)
        order.order_line.actual_delivery_date = date(2026, 1, 10)
        self.assertEqual(row.invoice_date, date(2026, 1, 25))
        self.assertEqual(row.rental_start, date(2026, 1, 10))
        self.assertEqual(row.manual_date_fields, ['invoice_date'])

    def test_period_start_repeated_edit_retains_original_key_without_duplicates(self):
        order = self._annual()
        row = self._rows(order)[0]
        initial_ids = set(order.billing_engine_line_ids.ids)
        for value in (date(2026, 2, 1), date(2026, 3, 1), date(2026, 1, 1)):
            row.with_user(self.salesperson).period_start = value
            order._sync_billing_engine()
            self.assertEqual(row.period_start, value)
            self.assertEqual(row.source_period_start, date(2026, 1, 1))
            self.assertEqual(set(order.billing_engine_line_ids.ids), initial_ids)

    def test_dates_locked_when_invoice_or_invoice_line_is_linked(self):
        order = self._order(months=1, user_id=self.salesperson.id)
        row = self._rows(order)
        order._generate_billing_engine_invoices()
        before = self._dates(row)
        with self.assertRaisesRegex(UserError, 'sudah memiliki invoice'):
            row.with_user(self.salesperson).invoice_date = date(2026, 2, 1)
        invoice = row.invoice_id
        row.sudo().write({'invoice_id': False})
        self.assertTrue(row.invoice_line_id)
        with self.assertRaises(UserError):
            row.with_user(self.salesperson).invoice_date = date(2026, 2, 1)
        self.assertEqual(self._dates(row), before)
        self.assertEqual(invoice.state, 'draft')

    def test_date_permissions_do_not_allow_amount_link_metadata_or_other_orders(self):
        order = self._annual()
        row = self._rows(order)[0].with_user(self.salesperson)
        for values in ({'amount': 1}, {'sale_line_id': order.order_line.id},
                       {'invoice_id': False}, {'source_period_start': date(2020, 1, 1)},
                       {'manual_date_fields': []}):
            with self.assertRaises(AccessError):
                row.with_context(_billing_sync_token=True).write(values)
        with self.assertRaises(AccessError):
            row.with_user(self.other_salesperson).invoice_date = date(2026, 1, 25)
        with self.assertRaises(AccessError):
            row.unlink()
        with self.assertRaises(AccessError):
            row.copy()

    def test_invalid_date_ranges_are_atomic(self):
        row = self._rows(self._annual())[0].with_user(self.salesperson)
        before = self._dates(row)
        for values in ({'period_end': date(2025, 1, 1)}, {'rental_end': date(2025, 1, 1)}):
            with self.assertRaises(UserError):
                row.write(values)
            self.assertEqual(self._dates(row), before)
        self.assertFalse(row.manual_date_fields)

    def test_form_dates_and_native_views_are_editable_without_financial_columns(self):
        row = self._rows(self._annual())[0].with_user(self.salesperson)
        with Form(row, view='x_sale_purchase_custom.view_sale_order_billing_engine_form') as form:
            form.invoice_date = date(2026, 1, 25)
        self.assertEqual(row.invoice_date, date(2026, 1, 25))
        view = row.get_view(view_type='list')
        root = etree.fromstring(view['arch'])
        self.assertEqual(root.get('editable'), 'bottom')
        self.assertEqual(root.get('create'), 'false')
        for name in ('period_start', 'period_end', 'rental_start', 'rental_end', 'invoice_date', 'invoice_draft_date'):
            self.assertIn('invoice_id', root.xpath("//field[@name='%s']" % name)[0].get('readonly'))

    def test_unmodified_dates_keep_automatic_forecast_behavior(self):
        order = self._order(months=1, user_id=self.salesperson.id)
        row = self._rows(order)
        self.assertFalse(row.manual_date_fields)
        original = row.invoice_date
        row.with_user(self.salesperson).invoice_date = original
        self.assertFalse(row.manual_date_fields)
        order.order_line.actual_delivery_date = date(2026, 1, 20)
        self.assertEqual(row.rental_start, date(2026, 1, 20))

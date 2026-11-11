from datetime import date, datetime

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestBillingEngineReturnDate(RentalBillingEngineInvoiceCommon):
    def test_empty_return_date_keeps_existing_schedule(self):
        order = self._order(months=3)
        before = order.billing_engine_line_ids.read([
            'rental_start', 'rental_end', 'total_days', 'amount', 'invoice_date', 'invoice_draft_date',
        ])
        order.order_line.bastk_return_date = False
        self.assertEqual(order.billing_engine_line_ids.read([
            'rental_start', 'rental_end', 'total_days', 'amount', 'invoice_date', 'invoice_draft_date',
        ]), before)

    def test_full_return_caps_last_cycle_and_removes_future_unbilled_rows(self):
        order = self._order(months=4)
        original = self._rows(order)
        first_values = original[0].read(['rental_start', 'rental_end', 'total_days', 'amount'])
        date_before = original[1].invoice_date
        order.order_line.bastk_return_date = date(2026, 2, 10)
        rows = self._rows(order)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].read(['rental_start', 'rental_end', 'total_days', 'amount']), first_values)
        self.assertEqual(rows[1].rental_start, date(2026, 2, 5))
        self.assertEqual(rows[1].rental_end, date(2026, 2, 10))
        self.assertEqual(rows[1].total_days, 6)
        self.assertEqual(rows[1].amount, 600000)
        self.assertEqual(rows[1].invoice_date, date_before)
        self.assertFalse(original[2:].exists())
        ids = rows.ids
        order._sync_billing_engine()
        self.assertEqual(self._rows(order).ids, ids)

    def test_prorate_return_uses_inclusive_calendar_days(self):
        order = self._order(months=4, billing_rule='prorate')
        order.order_line.bastk_return_date = date(2026, 2, 10)
        rows = self._rows(order)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].amount, order.currency_id.round(3000000 * 27 / 31))
        self.assertEqual(rows[1].rental_start, date(2026, 2, 1))
        self.assertEqual(rows[1].rental_end, date(2026, 2, 10))
        self.assertEqual(rows[1].total_days, 10)
        self.assertEqual(rows[1].amount, order.currency_id.round(3000000 * 10 / 28))

    def test_full_quarter_full_months_and_final_partial(self):
        order = self._order(months=12, invoicing_cycle_period='per_3_months', top_billing='dibelakang')
        invoice_date = self._rows(order)[0].invoice_date
        order.order_line.bastk_return_date = date(2026, 3, 14)
        row = self._rows(order)
        self.assertEqual(len(row), 1)
        self.assertEqual(row.rental_end, date(2026, 3, 14))
        self.assertEqual(row.total_days, 70)
        self.assertEqual(row.amount, 7000000)
        self.assertEqual(row.invoice_date, invoice_date)

    def test_prorate_quarter_stops_calendar_loop_at_return(self):
        order = self._order(months=12, billing_rule='prorate', invoicing_cycle_period='per_3_months')
        order.order_line.bastk_return_date = date(2026, 2, 10)
        row = self._rows(order)
        self.assertEqual(len(row), 1)
        self.assertEqual(row.rental_end, date(2026, 2, 10))
        self.assertEqual(row.total_days, 37)
        self.assertEqual(row.amount, order.currency_id.round(3000000 * (27 / 31 + 10 / 28)))

    def test_six_month_yearly_and_whole_duration_return(self):
        for frequency in ('per_6_months', 'yearly', 'as_duration'):
            order = self._order(months=24, invoicing_cycle_period=frequency)
            order.order_line.bastk_return_date = date(2026, 3, 6)
            row = self._rows(order)
            self.assertEqual(len(row), 1)
            self.assertEqual(row.rental_end, date(2026, 3, 6))
            self.assertEqual(row.total_days, 62)
            self.assertEqual(row.amount, 6200000)

    def test_return_on_delivery_counts_one_day_and_before_delivery_is_not_billed(self):
        for rule, expected in [('full_charge', 100000), ('prorate', 3000000 / 31)]:
            order = self._order(months=3, billing_rule=rule)
            order.order_line.bastk_return_date = date(2026, 1, 5)
            row = self._rows(order)
            self.assertEqual(len(row), 1)
            self.assertEqual(row.rental_start, date(2026, 1, 5))
            self.assertEqual(row.rental_end, date(2026, 1, 5))
            self.assertEqual(row.total_days, 1)
            self.assertEqual(row.amount, order.currency_id.round(expected))
            order.order_line.bastk_return_date = date(2026, 1, 4)
            self.assertFalse(self._rows(order))
            self.assertFalse(order._generate_billing_engine_invoices(batch_months=False))

    def test_return_at_cycle_boundary_does_not_add_an_extra_month(self):
        order = self._order(months=4)
        order.order_line.bastk_return_date = date(2026, 2, 4)
        row = self._rows(order)
        self.assertEqual(len(row), 1)
        self.assertEqual(row.rental_end, date(2026, 2, 4))
        self.assertEqual(row.amount, 3000000)
        order.order_line.bastk_return_date = date(2026, 2, 5)
        rows = self._rows(order)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1].amount, 100000)

    def test_month_end_anniversary_and_leap_year(self):
        order = self._order(start=datetime(2026, 1, 31, 5), months=4, delivery=date(2026, 1, 31))
        order.order_line.bastk_return_date = date(2026, 3, 15)
        rows = self._rows(order)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1].rental_start, date(2026, 2, 28))
        self.assertEqual(rows[1].rental_end, date(2026, 3, 15))
        self.assertEqual(rows[1].total_days, 16)
        self.assertEqual(rows[1].amount, 1600000)
        leap = self._order(start=datetime(2028, 2, 1, 5), months=3, delivery=date(2028, 2, 10), billing_rule='prorate')
        leap.order_line.bastk_return_date = date(2028, 2, 20)
        self.assertEqual(self._rows(leap).total_days, 11)
        self.assertEqual(self._rows(leap).amount, leap.currency_id.round(3000000 * 11 / 29))

    def test_late_return_never_extends_the_contract(self):
        for rule in ('full_charge', 'prorate'):
            order = self._order(months=3, billing_rule=rule)
            before = self._rows(order).read(['rental_end', 'total_days', 'amount'])
            order.order_line.bastk_return_date = date(2026, 12, 31)
            self.assertEqual(self._rows(order).read(['rental_end', 'total_days', 'amount']), before)

    def test_return_only_changes_the_returned_unit(self):
        order = self._order(months=4, order_line=[
            Command.create(self._line_values(delivery=date(2026, 1, 5))),
            Command.create(self._line_values(delivery=date(2026, 1, 12))),
        ])
        returned, active = order.order_line
        active_rows = order.billing_engine_line_ids.filtered(lambda row: row.sale_line_id == active)
        before = active_rows.read(['rental_start', 'rental_end', 'total_days', 'amount'])
        returned.bastk_return_date = date(2026, 2, 10)
        self.assertEqual(len(order.billing_engine_line_ids.filtered(lambda row: row.sale_line_id == returned)), 2)
        self.assertEqual(active_rows.read(['rental_start', 'rental_end', 'total_days', 'amount']), before)

    def test_clear_or_change_return_rebuilds_unbilled_forecast(self):
        order = self._order(months=4)
        order.order_line.bastk_return_date = date(2026, 2, 10)
        self.assertEqual(len(self._rows(order)), 2)
        order.order_line.bastk_return_date = date(2026, 3, 10)
        self.assertEqual(len(self._rows(order)), 3)
        order.order_line.bastk_return_date = False
        self.assertEqual(len(self._rows(order)), 4)
        self.assertTrue(all(row.amount == 3000000 for row in self._rows(order)))

    def test_generate_only_returned_last_period_and_no_future_invoices(self):
        order = self._order(months=12)
        order.order_line.bastk_return_date = date(2026, 2, 10)
        invoices = order._generate_billing_engine_invoices(batch_months=False)
        self.assertEqual(len(invoices), 2)
        self.assertEqual(sum(invoices.mapped('amount_untaxed')), 3600000)
        last = self._rows(order)[-1]
        self.assertIn('10-02-2026', last.invoice_line_id.name)
        self.assertEqual(last.invoice_line_id.price_subtotal, 600000)
        self.assertFalse(order._generate_billing_engine_invoices(batch_months=False))

    def test_existing_draft_and_posted_invoices_are_not_rewritten(self):
        for posted in (False, True):
            order = self._order(months=3)
            invoices = order._generate_billing_engine_invoices(batch_months=False)
            if posted:
                invoices.action_post()
            rows = self._rows(order)
            before_rows = rows.read(['rental_start', 'rental_end', 'total_days', 'amount', 'invoice_id'])
            before_moves = invoices.read(['amount_total', 'state', 'invoice_date'])
            before_lines = invoices.invoice_line_ids.read(['name', 'price_unit', 'quantity', 'price_subtotal'])
            order.order_line.bastk_return_date = date(2026, 1, 10)
            self.assertEqual(rows.read(['rental_start', 'rental_end', 'total_days', 'amount', 'invoice_id']), before_rows)
            self.assertEqual(invoices.read(['amount_total', 'state', 'invoice_date']), before_moves)
            self.assertEqual(invoices.invoice_line_ids.read(['name', 'price_unit', 'quantity', 'price_subtotal']), before_lines)
            self.assertFalse(order._generate_billing_engine_invoices(batch_months=False))

    def test_billed_first_month_preserved_while_last_unbilled_month_is_recalculated(self):
        order = self._order(months=6)
        first_invoice = order._generate_billing_engine_invoices(
            today=date(2026, 1, 31), current_month_only=True, batch_months=False,
        )
        self.assertEqual(len(first_invoice), 1)
        before = first_invoice.invoice_line_ids.read(['name', 'price_unit', 'quantity', 'price_subtotal'])
        order.order_line.bastk_return_date = date(2026, 2, 10)
        self.assertEqual(len(self._rows(order)), 2)
        last_invoice = order._generate_billing_engine_invoices(batch_months=False)
        self.assertEqual(len(last_invoice), 1)
        self.assertEqual(last_invoice.amount_untaxed, 600000)
        self.assertEqual(first_invoice.invoice_line_ids.read(['name', 'price_unit', 'quantity', 'price_subtotal']), before)

    def test_return_date_supplied_when_order_is_created(self):
        order = self._order(months=6, order_line=[Command.create(self._line_values(
            delivery=date(2026, 1, 5), bastk_return_date=date(2026, 2, 10),
        ))])
        self.assertEqual(len(self._rows(order)), 2)
        self.assertEqual(self._rows(order)[-1].rental_end, date(2026, 2, 10))
        self.assertEqual(self._rows(order)[-1].amount, 600000)

    def test_preexisting_manual_rental_dates_yield_to_actual_return_only(self):
        order = self._order(months=3)
        row = self._rows(order)[1]
        row.sudo().write({
            'rental_start': date(2026, 2, 2), 'rental_end': date(2026, 3, 25),
            'invoice_date': date(2026, 5, 8),
        })
        order.order_line.bastk_return_date = date(2026, 2, 10)
        self.assertEqual(row.rental_start, date(2026, 2, 5))
        self.assertEqual(row.rental_end, date(2026, 2, 10))
        self.assertEqual(row.amount, 600000)
        self.assertEqual(row.invoice_date, date(2026, 5, 8))
        self.assertEqual(row.manual_date_fields, ['invoice_date'])
        with self.assertRaises(UserError):
            row.write({'rental_end': date(2026, 3, 5)})
        with Form(row, view='x_sale_purchase_custom.view_sale_order_billing_engine_form') as form:
            self.assertTrue(form._get_modifier('rental_end', 'readonly'))

    def test_missing_delivery_keeps_zero_values_without_future_placeholders(self):
        order = self._order(months=4, delivery=False)
        order.order_line.bastk_return_date = date(2026, 2, 10)
        rows = self._rows(order)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not row.rental_start and not row.rental_end and row.amount == 0 for row in rows))
        self.assertFalse(order._generate_billing_engine_invoices(batch_months=False))

    def test_zero_monthly_rate_stays_zero_on_partial_return(self):
        order = self._order(months=3)
        order.order_line.price_unit = 0
        order.order_line.bastk_return_date = date(2026, 1, 10)
        row = self._rows(order)
        self.assertEqual(row.total_days, 6)
        self.assertEqual(row.amount, 0)

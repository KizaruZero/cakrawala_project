from datetime import date, datetime
from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestRentalBillingEngine(TransactionCase):
    """Exercise stored schedules through the same ORM entry points as the UI."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={
            **cls.env.context,
            'tracking_disable': True,
            'mail_create_nosubscribe': True,
            'tz': 'Asia/Jakarta',
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Billing Engine Test Customer'})
        cls.product = cls.env['product.product'].create({
            'name': 'Billing Engine Test Vehicle',
            'type': 'consu',
            'rent_ok': True,
            'list_price': 3000000,
            'taxes_id': [Command.clear()],
        })
        cls.rental_type = cls.env['sale.rental.type'].create({'name': 'Billing Engine Test Rental'})
        cls.plan = cls.env['account.analytic.plan'].create({'name': 'Billing Engine Test Units'})
        cls.unit_account = cls.env['account.analytic.account'].create({
            'name': 'B 1234 TEST',
            'plan_id': cls.plan.id,
            'company_id': cls.env.company.id,
        })
        cls.order_model = cls.env['sale.order']

    def _line_values(self, delivery=date(2026, 9, 25), **overrides):
        return {
            'product_id': self.product.id,
            'product_uom_qty': 1,
            'price_unit': 3000000,
            'tax_ids': [Command.clear()],
            'actual_delivery_date': delivery,
            'analytic_distribution': {str(self.unit_account.id): 100},
            **overrides,
        }

    def _order(self, start=datetime(2026, 9, 25, 5), months=36,
               delivery=date(2026, 9, 25), **overrides):
        values = {
            'partner_id': self.partner.id,
            'is_rental_order': True,
            'rental_type_id': self.rental_type.id,
            'rental_start_date': start,
            'rental_return_date': start + relativedelta(months=months) if start else False,
            'actual_rental_start_date': start,
            'masa_sewa_bulan': months,
            'billing_rule': 'full_charge',
            'invoicing_cycle_period': 'monthly',
            'invoicing_date_monthly': '20',
            'top_billing': 'didepan',
            'weekend_rule_adjustment': 'keep_original',
            'invoice_print_lead_time': 3,
            'state': 'sale',
            'order_line': [Command.create(self._line_values(delivery))],
            **overrides,
        }
        return self.order_model.create(values)

    def _rows(self, order):
        return order.billing_engine_line_ids.sorted(lambda row: (row.period_start, row.sale_line_id.id))

    def test_all_calendar_months_and_no_duplicate_regeneration(self):
        order = self._order()
        rows = self._rows(order)
        self.assertEqual(len(rows), 37)
        self.assertEqual(order.billing_engine_count, 37)
        self.assertEqual(rows[0].period_start, date(2026, 9, 1))
        self.assertEqual(rows[-1].period_start, date(2029, 9, 1))
        self.assertEqual(rows[-1].period_end, date(2029, 9, 30))
        self.assertEqual(rows[0].rental_start, date(2026, 9, 25))
        self.assertEqual(rows[0].rental_end, date(2026, 10, 25))
        self.assertEqual(rows[1].rental_start, date(2026, 10, 25))
        self.assertEqual(rows[1].rental_end, date(2026, 11, 24))
        self.assertTrue(all(row.total_days == 30 for row in rows))
        self.assertTrue(all(row.rate_monthly == 3000000 and row.amount == 3000000 for row in rows))
        self.assertTrue(all(row.product_id == self.product for row in rows))
        self.assertTrue(all(row.unit_plate_no == self.unit_account.name for row in rows))
        self.assertFalse(any(row.invoice_number or row.invoice_status for row in rows))
        original_ids = rows.ids
        order._sync_billing_engine()
        self.assertEqual(self._rows(order).ids, original_ids)
        self.assertEqual(order.action_view_billing_engine()['res_model'], 'sale.order.billing.engine')

    def test_invoicing_frequency_groups_calendar_months(self):
        for frequency, count, first_months, last_months in [
            ('per_3_months', 13, 3, 1),
            ('per_6_months', 7, 6, 1),
            ('yearly', 4, 12, 1),
            ('as_duration', 1, 37, 37),
        ]:
            with self.subTest(frequency=frequency):
                order = self._order(invoicing_cycle_period=frequency, top_billing='dibelakang')
                rows = self._rows(order)
                self.assertEqual(len(rows), count)
                self.assertEqual(rows[0].total_days, (rows[0].rental_end - rows[0].rental_start).days)
                self.assertEqual(
                    rows[0].rental_end,
                    rows[0].rental_start + relativedelta(months=first_months, days=-1),
                )
                self.assertEqual(rows[0].amount, 3000000 * first_months)
                self.assertEqual(rows[-1].amount, 3000000 * last_months)
                self.assertEqual(rows[0].invoice_date, date(2026, 9, 20) + relativedelta(months=first_months))

    def test_prorate_only_the_first_delivery_month(self):
        order = self._order(months=3, billing_rule='prorate', top_billing='dibelakang')
        rows = self._rows(order)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0].rental_start, date(2026, 9, 25))
        self.assertEqual(rows[0].rental_end, date(2026, 9, 30))
        self.assertEqual(rows[0].total_days, 5)
        self.assertEqual(rows[0].amount, 500000)
        self.assertEqual(rows[0].invoice_date, date(2026, 10, 20))
        self.assertEqual(rows[0].invoice_draft_date, date(2026, 10, 17))
        self.assertEqual(rows[1].rental_start, date(2026, 10, 1))
        self.assertEqual(rows[1].rental_end, date(2026, 10, 31))
        self.assertTrue(all(row.total_days == 30 and row.amount == 3000000 for row in rows[1:]))
        # The terminal partial calendar month is intentionally billed Full.
        self.assertEqual(rows[-1].amount, 3000000)

    def test_grouped_prorate_combines_first_partial_and_later_full_months(self):
        order = self._order(months=3, billing_rule='prorate', invoicing_cycle_period='per_3_months')
        rows = self._rows(order)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].total_days, 5 + 60)
        self.assertEqual(rows[0].rental_end, date(2026, 11, 30))
        self.assertEqual(rows[0].amount, 6500000)
        self.assertEqual(rows[-1].amount, 3000000)

    def test_leap_month_and_exclusive_actual_rental_endpoint(self):
        order = self._order(
            start=datetime(2028, 2, 10, 5), months=1,
            delivery=date(2028, 2, 10), billing_rule='prorate',
        )
        rows = self._rows(order)
        self.assertEqual(rows[0].total_days, 19)
        self.assertEqual(rows[0].rental_end, date(2028, 2, 29))
        self.assertEqual(rows[0].amount, order.currency_id.round(3000000 * 19 / 29))
        # To on the first of a month does not include that entire extra month.
        first_day = self._order(start=datetime(2026, 9, 1, 5), months=3, delivery=date(2026, 9, 1))
        self.assertEqual(len(first_day.billing_engine_line_ids), 3)
        self.assertEqual(self._rows(first_day)[-1].period_start, date(2026, 11, 1))

    def test_invoice_day_weekend_and_calendar_lead_time(self):
        order = self._order(
            start=datetime(2027, 1, 5, 5), months=1, delivery=date(2027, 1, 5),
            invoicing_date_monthly='31', weekend_rule_adjustment='next_working_day',
        )
        rows = self._rows(order)
        # 31 January 2027 is Sunday, so the adjusted date is Monday, 1 February.
        self.assertEqual(rows[0].invoice_date, date(2027, 2, 1))
        self.assertEqual(rows[0].invoice_draft_date, date(2027, 1, 29))
        self.assertEqual(rows[1].invoice_date, date(2027, 3, 1))
        order.write({'weekend_rule_adjustment': 'previous_working_day'})
        self.assertEqual(self._rows(order)[0].invoice_date, date(2027, 1, 29))
        order.write({'weekend_rule_adjustment': 'keep_original'})
        self.assertEqual(self._rows(order)[0].invoice_date, date(2027, 1, 31))
        self.assertEqual(self._rows(order)[1].invoice_date, date(2027, 2, 28))

    def test_month_end_anniversary_does_not_drift(self):
        order = self._order(
            start=datetime(2027, 1, 31, 5), months=2, delivery=date(2027, 1, 31),
            invoicing_date_monthly=False,
        )
        rows = self._rows(order)
        self.assertEqual(rows.mapped('rental_start'), [date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31)])
        self.assertEqual(rows.mapped('invoice_date'), [date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31)])

    def test_missing_input_dates_and_late_delivery_refresh(self):
        order = self._order(start=False, months=1, delivery=False)
        self.assertFalse(order.billing_engine_line_ids)
        order.write({'actual_rental_start_date': datetime(2026, 9, 25, 5)})
        rows = self._rows(order)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row.rate_monthly == 3000000 for row in rows))
        self.assertFalse(any(row.rental_start or row.rental_end or row.invoice_date for row in rows))
        self.assertTrue(all(row.total_days == 0 and row.amount == 0 for row in rows))
        original_ids = rows.ids
        order.order_line.write({'actual_delivery_date': date(2026, 9, 25)})
        self.assertEqual(self._rows(order).ids, original_ids)
        self.assertEqual(self._rows(order)[0].rental_start, date(2026, 9, 25))
        self.assertEqual(self._rows(order)[0].amount, 3000000)
        order.write({'masa_sewa_bulan': 2})
        self.assertEqual(len(order.billing_engine_line_ids), 3)

    def test_confirmation_excludes_notes_zero_quantity_and_downpayment(self):
        order = self._order(months=1, state='draft', order_line=[
            Command.create(self._line_values()),
            Command.create(self._line_values(product_uom_qty=0)),
            Command.create(self._line_values(is_downpayment=True)),
            Command.create({'display_type': 'line_section', 'name': 'Billing Engine Notes'}),
        ])
        self.assertFalse(order.billing_engine_line_ids)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(len(order.billing_engine_line_ids), 2)
        billed_lines = order.billing_engine_line_ids.sale_line_id
        self.assertEqual(billed_lines, order.order_line.filtered(lambda line: not line.display_type and not line.is_downpayment and line.product_uom_qty))
        self.assertFalse(order.invoice_ids)

    def test_multi_plan_analytic_distribution_prefers_vehicle_plate(self):
        if 'license_plate' not in self.unit_account._fields:
            self.skipTest('Vehicle license plate analytic extension is not installed.')
        self.unit_account.write({'license_plate': 'B 9876 UNIT'})
        department_plan = self.env['account.analytic.plan'].create({'name': 'Billing Engine Test Department'})
        department = self.env['account.analytic.account'].create({
            'name': 'Administration', 'plan_id': department_plan.id,
            'company_id': self.env.company.id,
        })
        order = self._order(months=1, order_line=[Command.create(self._line_values(
            analytic_distribution={f'{department.id},{self.unit_account.id}': 100},
        ))])
        self.assertEqual(set(order.billing_engine_line_ids.mapped('unit_plate_no')), {'B 9876 UNIT'})

    def test_sales_user_readonly_forecast_and_internal_delivery_refresh(self):
        # Access control does not depend on avatar attachments or the filestore.
        with patch.object(type(self.env['res.partner']), '_avatar_generate_svg', return_value=False):
            salesperson = new_test_user(
                self.env, login='billing_engine_sales_user',
                groups='sales_team.group_sale_salesman', company_id=self.env.company.id,
            )
            other_salesperson = new_test_user(
                self.env, login='billing_engine_other_sales_user',
                groups='sales_team.group_sale_salesman', company_id=self.env.company.id,
            )
        own_order = self._order(months=1, delivery=False, user_id=salesperson.id)
        other_order = self._order(months=1, user_id=other_salesperson.id)
        Engine = self.env['sale.order.billing.engine'].with_user(salesperson)
        own_rows = self._rows(own_order)
        other_rows = self._rows(other_order)
        visible = Engine.search([('id', 'in', (own_rows | other_rows).ids)])
        self.assertEqual(set(visible.ids), set(own_rows.ids))
        self.assertEqual(own_order.with_user(salesperson).billing_engine_count, 2)
        own_rows.with_user(salesperson).read(['period', 'rate_monthly', 'amount'])
        with self.assertRaises(AccessError):
            other_rows.with_user(salesperson).read(['amount'])

        # Users edit the source order line; internal sync may update the forecast.
        own_order.order_line.with_user(salesperson).write({
            'actual_delivery_date': date(2026, 9, 25),
        })
        refreshed = Engine.search([('order_id', '=', own_order.id)])
        self.assertEqual(set(refreshed.ids), set(own_rows.ids))
        self.assertTrue(all(row.amount == 3000000 for row in refreshed))
        self.assertTrue(all(row.rental_start for row in refreshed))

        with self.assertRaises(AccessError):
            Engine.create({
                'order_id': own_order.id,
                'sale_line_id': own_order.order_line.id,
                'period_start': date(2030, 1, 1),
                'period_end': date(2030, 1, 31),
            })
        with self.assertRaises(AccessError):
            refreshed[:1].write({'amount': 1})
        with self.assertRaises(AccessError):
            refreshed[:1].unlink()

    def test_source_changes_update_rows_and_frequency_removes_obsolete_periods(self):
        order = self._order(months=3)
        original_rows = self._rows(order)
        self.assertEqual(len(original_rows), 4)
        replacement_values = {
            'name': 'B 9999 TEST', 'plan_id': self.plan.id,
            'company_id': self.env.company.id,
        }
        if 'license_plate' in self.unit_account._fields:
            replacement_values['license_plate'] = 'B 9999 TEST'
        replacement_account = self.env['account.analytic.account'].create(replacement_values)
        order.order_line.write({
            'price_unit': 4000000,
            'analytic_distribution': {str(replacement_account.id): 100},
        })
        updated_rows = self._rows(order)
        self.assertEqual(updated_rows.ids, original_rows.ids)
        self.assertTrue(all(row.rate_monthly == 4000000 and row.amount == 4000000 for row in updated_rows))
        self.assertEqual(set(updated_rows.mapped('unit_plate_no')), {'B 9999 TEST'})
        self.assertEqual(updated_rows.analytic_account_id, replacement_account)

        order.write({'invoicing_cycle_period': 'per_3_months'})
        grouped_rows = self._rows(order)
        self.assertEqual(grouped_rows.ids, [original_rows[0].id, original_rows[3].id])
        self.assertEqual(grouped_rows.mapped('period_start'), [date(2026, 9, 1), date(2026, 12, 1)])
        self.assertEqual(grouped_rows.mapped('amount'), [12000000, 4000000])
        self.assertFalse(original_rows[1:3].exists())
        self.assertEqual(order.billing_engine_count, 2)
        order._sync_billing_engine()
        self.assertEqual(self._rows(order).ids, grouped_rows.ids)

    def test_viewer_timezone_does_not_change_stored_contract_months(self):
        self.env.company.partner_id.write({'tz': 'Asia/Jakarta'})
        # 31 August 17:00 UTC is 1 September midnight in the company's timezone.
        order = self._order(
            start=datetime(2026, 8, 31, 17), months=12,
            delivery=date(2026, 9, 1),
        )
        rows = self._rows(order)
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0].period_start, date(2026, 9, 1))
        self.assertEqual(rows[-1].period_start, date(2027, 8, 1))
        original_ids = rows.ids
        original_periods = rows.mapped('period_start')

        foreign_viewer_order = order.with_context(tz='America/New_York')
        foreign_viewer_order.action_view_billing_engine()
        foreign_viewer_order._sync_billing_engine()
        refreshed = self._rows(foreign_viewer_order)
        self.assertEqual(refreshed.ids, original_ids)
        self.assertEqual(refreshed.mapped('period_start'), original_periods)
        self.assertEqual(foreign_viewer_order.billing_engine_count, 12)

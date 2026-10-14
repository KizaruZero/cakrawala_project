from datetime import date, datetime
from unittest.mock import patch

from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user

from .test_billing_engine import TestRentalBillingEngine


@tagged('post_install', '-at_install')
class TestRentalBillingEngineInvoices(TransactionCase):
    """Invoice the schedule without posting or changing real customer records."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={
            **cls.env.context,
            'tracking_disable': True,
            'mail_create_nosubscribe': True,
            'tz': 'Asia/Jakarta',
        })
        cls.company = cls.env.company
        cls.company.partner_id.tz = 'Asia/Jakarta'
        cls.income_account = cls.env['account.account'].create({
            'name': 'Billing Engine Test Income',
            'code': '799990001',
            'account_type': 'income',
            'company_ids': [Command.set(cls.company.ids)],
        })
        cls.receivable_account = cls.env['account.account'].create({
            'name': 'Billing Engine Test Receivable',
            'code': '799990002',
            'account_type': 'asset_receivable',
            'reconcile': True,
            'company_ids': [Command.set(cls.company.ids)],
        })
        cls.journal = cls.env['account.journal'].create({
            'name': 'Billing Engine Test Sales',
            'code': 'BEINV',
            'type': 'sale',
            'company_id': cls.company.id,
            'default_account_id': cls.income_account.id,
        })
        cls.payment_term = cls.env['account.payment.term'].create({
            'name': 'Billing Engine Test 30 Days',
            'company_id': cls.company.id,
            'line_ids': [Command.create({'value': 'percent', 'value_amount': 100, 'nb_days': 30})],
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Billing Engine Invoice Test Customer',
            'property_account_receivable_id': cls.receivable_account.id,
            'property_payment_term_id': cls.payment_term.id,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Billing Engine Invoice Test Vehicle',
            'type': 'consu',
            'rent_ok': True,
            'list_price': 3000000,
            'property_account_income_id': cls.income_account.id,
            'taxes_id': [Command.clear()],
        })
        cls.rental_type = cls.env['sale.rental.type'].create({
            'name': 'Billing Engine Invoice Test Rental',
        })
        cls.plan = cls.env['account.analytic.plan'].create({
            'name': 'Billing Engine Invoice Test Units',
        })
        cls.unit_account = cls.env['account.analytic.account'].create({
            'name': 'B 1234 INVOICE',
            'plan_id': cls.plan.id,
            'company_id': cls.company.id,
        })
        cls.order_model = cls.env['sale.order']

    # Share fixture builders, not the old TestCase's test methods.
    _line_values = TestRentalBillingEngine._line_values
    _rows = TestRentalBillingEngine._rows

    def _order(self, start=datetime(2026, 1, 1, 5), months=2,
               delivery=date(2026, 1, 5), **overrides):
        return TestRentalBillingEngine._order(
            self, start=start, months=months, delivery=delivery,
            **{
                'grouping_invoice': 'all_units',
                'journal_id': self.journal.id,
                'payment_term_id': self.payment_term.id,
                **overrides,
            },
        )

    def test_all_units_one_draft_invoice_per_calendar_period(self):
        order = self._order(
            top_billing='dibelakang',
            order_line=[Command.create(self._line_values(date(2026, 1, day)))
                        for day in (5, 16, 23)],
        )
        invoices = order._generate_billing_engine_invoices()
        self.assertEqual(len(invoices), 2)
        self.assertEqual(set(invoices.mapped('state')), {'draft'})
        self.assertEqual(set(invoices.mapped('move_type')), {'out_invoice'})
        self.assertTrue(all(invoice.x_is_rental_invoice for invoice in invoices))
        self.assertEqual(set(invoices.mapped('invoice_date')), {
            date(2026, 2, 20), date(2026, 3, 20),
        })
        self.assertTrue(all(len(invoice.invoice_line_ids) == 3 for invoice in invoices))
        self.assertTrue(all(invoice.amount_untaxed == 9000000 for invoice in invoices))
        self.assertEqual(set(invoices.invoice_line_ids.sale_line_ids.ids), set(order.order_line.ids))
        self.assertTrue(all(row.invoice_id and row.invoice_line_id for row in self._rows(order)))
        self.assertTrue(all(row.invoice_line_id.move_id == row.invoice_id
                            for row in self._rows(order)))

    def test_separate_same_day_month_grouped_different_delivery_separated(self):
        order = self._order(
            grouping_invoice='delivered_date', top_billing='dibelakang',
            order_line=[Command.create(self._line_values(date(2026, 1, day)))
                        for day in (5, 5, 16)],
        )
        invoices = order._generate_billing_engine_invoices()
        self.assertEqual(len(invoices), 4)
        january_rows = self._rows(order).filtered(lambda row: row.period_start == date(2026, 1, 1))
        self.assertEqual(january_rows[:2].invoice_id, january_rows[0].invoice_id)
        self.assertNotEqual(january_rows[-1].invoice_id, january_rows[0].invoice_id)
        self.assertEqual(sorted(len(invoice.invoice_line_ids) for invoice in invoices), [1, 1, 2, 2])
        self.assertEqual(january_rows[0].invoice_id.invoice_date, date(2026, 2, 20))
        self.assertEqual(january_rows[-1].invoice_id.invoice_date, date(2026, 2, 20))
        february_rows = self._rows(order).filtered(lambda row: row.period_start == date(2026, 2, 1))
        self.assertEqual(set(february_rows.mapped('invoice_date')), {
            date(2026, 3, 5), date(2026, 3, 16),
        })

    def test_separate_front_first_uses_invoicing_day_later_start_plus_one(self):
        order = self._order(grouping_invoice='delivered_date', top_billing='didepan')
        rows = self._rows(order)
        self.assertEqual(rows[0].invoice_date, date(2026, 1, 20))
        self.assertEqual(rows[0].invoice_draft_date, date(2026, 1, 17))
        self.assertEqual(rows[1].invoice_date, date(2026, 2, 6))
        invoices = order._generate_billing_engine_invoices()
        self.assertEqual(set(invoices.mapped('invoice_date')), {
            date(2026, 1, 20), date(2026, 2, 6),
        })

    def test_separate_first_date_weekend_adjustment_then_preparation_lead(self):
        # The first Invoicing Day is Saturday, 10 January 2026.
        order = self._order(
            delivery=date(2026, 1, 9), grouping_invoice='delivered_date',
            top_billing='didepan', weekend_rule_adjustment='next_working_day',
            invoicing_date_monthly='10',
        )
        first = self._rows(order)[0]
        self.assertEqual(first.invoice_date, date(2026, 1, 12))
        self.assertEqual(first.invoice_draft_date, date(2026, 1, 9))
        order.write({'weekend_rule_adjustment': 'previous_working_day'})
        self.assertEqual(first.invoice_date, date(2026, 1, 9))
        self.assertEqual(first.invoice_draft_date, date(2026, 1, 6))

    def test_quarterly_full_dates_and_amount_match_workbook(self):
        order = self._order(
            months=6, delivery=date(2026, 1, 5), invoicing_cycle_period='per_3_months',
            grouping_invoice='all_units', top_billing='dibelakang', invoicing_date_monthly='7',
        )
        rows = self._rows(order)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].rental_start, date(2026, 1, 5))
        self.assertEqual(rows[0].rental_end, date(2026, 4, 4))
        self.assertEqual(rows[0].total_days, 89)
        self.assertEqual(rows[1].rental_start, date(2026, 4, 5))
        self.assertEqual(rows[1].rental_end, date(2026, 7, 4))
        self.assertEqual(rows[1].total_days, 90)
        self.assertEqual(rows.mapped('amount'), [9000000, 9000000])
        self.assertEqual(rows.mapped('invoice_date'), [date(2026, 4, 7), date(2026, 7, 7)])
        invoices = order._generate_billing_engine_invoices()
        self.assertEqual(len(invoices), 2)
        self.assertEqual(invoices.invoice_line_ids.mapped('price_unit'), [9000000, 9000000])

    def test_quarterly_separate_first_invoicing_day_later_end_plus_one(self):
        order = self._order(
            months=6, delivery=date(2026, 1, 16), invoicing_cycle_period='per_3_months',
            grouping_invoice='delivered_date', top_billing='dibelakang', invoicing_date_monthly='7',
        )
        rows = self._rows(order)
        self.assertEqual(rows[0].rental_end, date(2026, 4, 15))
        self.assertEqual(rows.mapped('invoice_date'), [date(2026, 4, 7), date(2026, 7, 16)])
        self.assertEqual(rows[0].invoice_draft_date, date(2026, 4, 4))
        invoices = order._generate_billing_engine_invoices()
        self.assertEqual(set(invoices.mapped('invoice_date')), {date(2026, 4, 7), date(2026, 7, 16)})
        other_delivery_order = self._order(
            months=6, delivery=date(2026, 1, 5), invoicing_cycle_period='per_3_months',
            grouping_invoice='delivered_date', top_billing='dibelakang', invoicing_date_monthly='7',
        )
        self.assertEqual(self._rows(other_delivery_order).mapped('invoice_date'),
                         [date(2026, 4, 7), date(2026, 7, 5)])

    def test_separate_front_later_start_plus_one_even_after_invoicing_day(self):
        order = self._order(
            delivery=date(2026, 1, 25), grouping_invoice='delivered_date',
            top_billing='didepan', invoicing_date_monthly='7',
        )
        rows = self._rows(order)
        self.assertEqual(rows[0].invoice_date, date(2026, 1, 7))
        self.assertEqual(rows[1].rental_start, date(2026, 2, 25))
        self.assertEqual(rows[1].invoice_date, date(2026, 2, 26))
        self.assertEqual(rows[1].invoice_draft_date, date(2026, 2, 23))
        invoices = order._generate_billing_engine_invoices(today=date(2026, 2, 1))
        self.assertEqual(set(invoices.mapped('invoice_date')), {
            date(2026, 1, 7), date(2026, 2, 26),
        })

    def test_separate_subsequent_weekend_override_then_preparation_lead(self):
        # Subsequent Rental Start + 1 is Saturday, 7 February; Invoicing Day
        # is the 3rd, but only the first cycle follows that configured day.
        order = self._order(
            delivery=date(2026, 1, 6), grouping_invoice='delivered_date',
            top_billing='didepan', invoicing_date_monthly='3',
            weekend_rule_adjustment='next_working_day',
        )
        second = self._rows(order)[1]
        self.assertEqual(second.rental_start, date(2026, 2, 6))
        self.assertEqual(second.invoice_date, date(2026, 2, 9))
        self.assertEqual(second.invoice_draft_date, date(2026, 2, 6))
        order.write({'weekend_rule_adjustment': 'previous_working_day'})
        self.assertEqual(second.invoice_date, date(2026, 2, 6))
        self.assertEqual(second.invoice_draft_date, date(2026, 2, 3))
        order.write({'weekend_rule_adjustment': 'keep_original'})
        self.assertEqual(second.invoice_date, date(2026, 2, 7))
        self.assertEqual(second.invoice_draft_date, date(2026, 2, 4))

    def test_quarterly_current_month_horizon_uses_invoice_month_not_period_end(self):
        order = self._order(
            months=6, delivery=date(2026, 1, 16), invoicing_cycle_period='per_3_months',
            grouping_invoice='delivered_date', top_billing='dibelakang', invoicing_date_monthly='7',
        )
        first, second = self._rows(order)
        self.assertEqual(first.period_end, date(2026, 3, 31))
        self.assertEqual(first.invoice_date, date(2026, 4, 7))
        self.assertFalse(order._generate_billing_engine_invoices(today=date(2026, 3, 31)))
        invoice = order._generate_billing_engine_invoices(today=date(2026, 4, 1))
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.invoice_date, date(2026, 4, 7))
        self.assertEqual(invoice.amount_untaxed, 9000000)
        self.assertEqual(first.invoice_id, invoice)
        self.assertFalse(second.invoice_id)

    def test_delivery_before_contract_first_cycle_still_uses_invoicing_day(self):
        order = self._order(
            delivery=date(2025, 12, 16), grouping_invoice='delivered_date',
            top_billing='dibelakang', invoicing_date_monthly='7',
        )
        first, second = self._rows(order)
        self.assertEqual(first.period_start, date(2026, 1, 1))
        self.assertEqual(first.rental_start, date(2026, 1, 16))
        self.assertEqual(first.invoice_date, date(2026, 2, 7))
        self.assertEqual(second.rental_start, date(2026, 2, 16))
        self.assertEqual(second.rental_end, date(2026, 3, 15))
        self.assertEqual(second.invoice_date, date(2026, 3, 16))

    def test_quarterly_prorate_first_partial_month_then_full_following_quarter(self):
        order = self._order(
            months=6, delivery=date(2026, 1, 5), invoicing_cycle_period='per_3_months',
            billing_rule='prorate', top_billing='dibelakang',
        )
        rows = self._rows(order)
        self.assertEqual(rows[0].rental_end, date(2026, 3, 31))
        self.assertEqual(rows[0].total_days, 27 + 60)
        self.assertEqual(rows[0].amount, order.currency_id.round(3000000 * (27 / 31 + 2)))
        self.assertEqual(rows[1].total_days, 90)
        self.assertEqual(rows[1].amount, 9000000)
        invoices = order._generate_billing_engine_invoices()
        self.assertEqual(set(invoices.invoice_line_ids.mapped('price_unit')), set(rows.mapped('amount')))

    def test_repeat_generate_does_not_duplicate_draft_invoices(self):
        order = self._order()
        invoices = order._generate_billing_engine_invoices()
        row_ids = self._rows(order).ids
        self.assertFalse(order._generate_billing_engine_invoices())
        self.assertEqual(set(self._rows(order).invoice_id.ids), set(invoices.ids))
        self.assertEqual(self._rows(order).ids, row_ids)
        self.assertEqual(set(order.invoice_ids.ids), set(invoices.ids))

    def test_due_cutoff_uses_preparation_date_and_all_includes_future_periods(self):
        order = self._order(top_billing='didepan')
        self.assertFalse(order._generate_billing_engine_invoices(
            today=date(2026, 1, 16), due_only=True,
        ))
        due = order._generate_billing_engine_invoices(today=date(2026, 1, 17), due_only=True)
        self.assertEqual(len(due), 1)
        self.assertEqual(due.invoice_date, date(2026, 1, 20))
        self.assertFalse(order._generate_billing_engine_invoices(
            today=date(2026, 1, 17), due_only=True,
        ))
        self.assertFalse(order._generate_billing_engine_invoices(today=date(2026, 1, 17)))
        future = order._generate_billing_engine_invoices(
            today=date(2026, 1, 17), current_month_only=False,
        )
        self.assertEqual(len(future), 1)
        self.assertEqual(future.invoice_date, date(2026, 2, 20))

    def test_current_month_horizon_includes_prior_uninvoiced_not_future_months(self):
        order = self._order(months=6, top_billing='didepan')
        invoices = order._generate_billing_engine_invoices(today=date(2026, 3, 10))
        self.assertEqual(len(invoices), 3)
        self.assertEqual(set(invoices.mapped('invoice_date')), {
            date(2026, 1, 20), date(2026, 2, 20), date(2026, 3, 20),
        })
        self.assertTrue(all(not row.invoice_id for row in self._rows(order)[3:]))
        self.assertFalse(order._generate_billing_engine_invoices(today=date(2026, 3, 10)))
        behind = self._order(months=2, top_billing='dibelakang')
        february_invoices = behind._generate_billing_engine_invoices(today=date(2026, 2, 10))
        self.assertEqual(len(february_invoices), 1)
        self.assertEqual(february_invoices.invoice_date, date(2026, 2, 20))
        self.assertEqual(self._rows(behind)[0].invoice_id, february_invoices)
        self.assertFalse(self._rows(behind)[1].invoice_id)

    def test_same_customer_and_period_never_merge_different_orders(self):
        first = self._order(months=1)
        second = self._order(months=1)
        invoices = (first | second)._generate_billing_engine_invoices()
        self.assertEqual(len(invoices), 2)
        self.assertEqual(set(invoices.mapped('invoice_origin')), {first.name, second.name})
        self.assertNotEqual(first.billing_engine_line_ids.invoice_id, second.billing_engine_line_ids.invoice_id)

    def test_native_metadata_tax_analytic_and_sales_links_are_preserved(self):
        tax = self.env['account.tax'].create({
            'name': 'Billing Engine Invoice Test 10%',
            'amount_type': 'percent', 'amount': 10,
            'type_tax_use': 'sale', 'company_id': self.company.id,
        })
        order = self._order(months=1, order_line=[Command.create(self._line_values(
            date(2026, 1, 5), tax_ids=[Command.set(tax.ids)], discount=25,
        ))])
        invoice = order._generate_billing_engine_invoices()
        invoice_line = invoice.invoice_line_ids
        self.assertEqual(invoice.partner_id, order.partner_invoice_id)
        self.assertEqual(invoice.invoice_payment_term_id, self.payment_term)
        self.assertEqual(invoice.company_id, order.company_id)
        self.assertEqual(invoice.currency_id, order.currency_id)
        self.assertEqual(invoice.journal_id, self.journal)
        self.assertEqual(invoice.invoice_origin, order.name)
        self.assertEqual(invoice_line.sale_line_ids, order.order_line)
        self.assertEqual(invoice_line.product_id, self.product)
        self.assertEqual(invoice_line.account_id, self.income_account)
        self.assertEqual(invoice_line.tax_ids, tax)
        self.assertEqual(invoice_line.analytic_distribution, order.order_line.analytic_distribution)
        self.assertEqual(invoice_line.quantity, 1)
        self.assertEqual(invoice_line.discount, 0)
        self.assertEqual(invoice_line.price_unit, order.billing_engine_line_ids.amount)
        self.assertEqual(invoice.amount_untaxed, 3000000)
        self.assertEqual(invoice.amount_total, 3300000)

    def test_invoiced_snapshots_frozen_uninvoiced_rows_refresh(self):
        order = self._order()
        invoice = order._generate_billing_engine_invoices(today=date(2026, 1, 17), due_only=True)
        first, second = self._rows(order)
        snapshot = (first.amount, first.rental_start, first.rental_end, first.invoice_date)
        order.order_line.write({'price_unit': 4000000, 'actual_delivery_date': date(2026, 1, 8)})
        self.assertEqual((first.amount, first.rental_start, first.rental_end, first.invoice_date), snapshot)
        self.assertEqual(first.invoice_id, invoice)
        self.assertEqual(first.invoice_line_id.price_unit, 3000000)
        self.assertEqual(second.amount, 4000000)
        self.assertEqual(second.rental_start, date(2026, 2, 8))

    def test_contract_frequency_and_grouping_guard_after_linked_invoice(self):
        order = self._order()
        order._generate_billing_engine_invoices(today=date(2026, 1, 17), due_only=True)
        for values in (
            {'invoicing_cycle_period': 'per_3_months'},
            {'masa_sewa_bulan': 3},
            {'actual_rental_start_date': datetime(2026, 2, 1, 5)},
            {'grouping_invoice': 'delivered_date'},
        ):
            with self.subTest(values=values):
                with self.assertRaises(UserError), self.cr.savepoint():
                    order.write(values)

    def test_cancelled_link_retained_draft_deletion_allows_regeneration(self):
        order = self._order()
        order._generate_billing_engine_invoices()
        first, second = self._rows(order)
        cancelled = first.invoice_id
        cancelled.button_cancel()
        self.assertEqual(first.invoice_id, cancelled)
        self.assertTrue(first.invoice_status)
        self.assertFalse(order._generate_billing_engine_invoices())
        deleted_id = second.invoice_id.id
        second.invoice_id.unlink()
        self.assertFalse(second.invoice_id)
        self.assertFalse(second.invoice_line_id)
        regenerated = order._generate_billing_engine_invoices()
        self.assertEqual(len(regenerated), 1)
        self.assertNotEqual(regenerated.id, deleted_id)
        self.assertEqual(second.invoice_id, regenerated)
        self.assertEqual(first.invoice_id, cancelled)

    def test_legacy_due_generator_shares_engine_invoice_linkage(self):
        order = self._order()
        order._generate_rental_invoices_if_due(date(2026, 1, 17))
        rows = self._rows(order)
        self.assertTrue(rows[0].invoice_id)
        self.assertFalse(rows[1].invoice_id)
        self.assertFalse(order._generate_billing_engine_invoices(
            today=date(2026, 1, 17), due_only=True,
        ))
        order._generate_rental_invoices_if_due(date(2026, 1, 17), trigger_all=True)
        self.assertTrue(rows[1].invoice_id)
        self.assertEqual(len(order.invoice_ids), 2)

    def test_legacy_preparation_can_cross_month_manual_invoice_horizon_does_not(self):
        order = self._order(
            months=1, top_billing='dibelakang', invoicing_date_monthly='1',
            invoice_print_lead_time=3,
        )
        row = order.billing_engine_line_ids
        self.assertEqual(row.invoice_date, date(2026, 2, 1))
        self.assertEqual(row.invoice_draft_date, date(2026, 1, 29))
        self.assertFalse(order._generate_billing_engine_invoices(today=date(2026, 1, 29)))
        self.assertFalse(order._generate_rental_invoices_if_due(date(2026, 1, 28)))
        self.assertFalse(row.invoice_id)
        invoice = order._generate_rental_invoices_if_due(date(2026, 1, 29))
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.invoice_date, date(2026, 2, 1))
        self.assertEqual(row.invoice_id, invoice)
        self.assertFalse(order._generate_rental_invoices_if_due(date(2026, 1, 29)))

    def test_missing_delivery_and_unconfirmed_orders_not_invoiced(self):
        no_delivery = self._order(delivery=False)
        draft = self._order(state='draft')
        normal = self._order(is_rental_order=False)
        self.assertFalse((no_delivery | draft | normal)._generate_billing_engine_invoices())
        self.assertFalse(no_delivery.invoice_ids | draft.invoice_ids | normal.invoice_ids)

    def test_wizard_has_exactly_two_buttons_and_menu_directly_below_orders(self):
        view = self.env.ref('x_sale_purchase_custom.view_billing_engine_invoice_wizard_form')
        arch = etree.fromstring(view.arch_db.encode())
        self.assertEqual([button.get('string') for button in arch.xpath('//footer/button')],
                         ['Generate', 'Cancel'])
        self.assertIn('Billing Engine', ''.join(arch.itertext()))
        action = self.env.ref('x_sale_purchase_custom.action_billing_engine_invoice_wizard')
        self.assertEqual(action.target, 'new')
        menu = self.env.ref('x_sale_purchase_custom.menu_billing_engine_generate_invoices')
        orders_menu = self.env.ref('sale_renting.rental_orders_all')
        self.assertEqual(menu.parent_id, orders_menu.parent_id)
        self.assertEqual(menu.sequence, orders_menu.sequence + 1)
        wizard = self.env['rental.billing.engine.invoice.wizard'].create({})
        with patch.object(type(self.order_model), '_generate_billing_engine_invoices',
                          return_value=self.env['account.move']) as generate:
            result = wizard.action_generate()
        generate.assert_called_once()
        self.assertEqual(result['tag'], 'display_notification')

    def test_wizard_returns_only_newly_created_invoice_action(self):
        order = self._order(months=1)
        invoice = order._generate_billing_engine_invoices()
        wizard = self.env['rental.billing.engine.invoice.wizard'].create({})
        with patch.object(type(self.order_model), '_generate_billing_engine_invoices', return_value=invoice):
            action = wizard.action_generate()
        self.assertEqual(action['res_model'], 'account.move')
        self.assertEqual(action['domain'], [('id', 'in', invoice.ids)])

    def test_late_delivery_appends_existing_period_draft_not_another_invoice(self):
        order = self._order(months=1, order_line=[
            Command.create(self._line_values(date(2026, 1, 5))),
            Command.create(self._line_values(False)),
        ])
        invoice = order._generate_billing_engine_invoices(today=date(2026, 1, 17))
        self.assertEqual(len(invoice), 1)
        self.assertEqual(len(invoice.invoice_line_ids), 1)
        waiting_line = order.order_line.filtered(lambda line: not line.actual_delivery_date)
        waiting_line.write({'actual_delivery_date': date(2026, 1, 16)})
        modified = order._generate_billing_engine_invoices(today=date(2026, 1, 17))
        self.assertEqual(modified, invoice)
        self.assertEqual(order.invoice_ids, invoice)
        self.assertEqual(len(invoice.invoice_line_ids), 2)
        self.assertEqual(invoice.amount_untaxed, 6000000)
        self.assertEqual(self._rows(order).invoice_id, invoice)
        self.assertEqual(len(self._rows(order).invoice_line_id), 2)
        self.assertFalse(order._generate_billing_engine_invoices(today=date(2026, 1, 17)))

    def test_native_post_and_reset_draft_update_engine_invoice_details(self):
        order = self._order(months=1)
        invoice = order._generate_billing_engine_invoices()
        row = order.billing_engine_line_ids
        draft_status = row.invoice_status
        self.assertTrue(draft_status)
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')
        self.assertTrue(invoice.name and invoice.name != '/')
        self.assertEqual(row.invoice_number, invoice.name)
        self.assertNotEqual(row.invoice_status, draft_status)
        labels = dict(invoice._fields['status_in_payment']._description_selection(self.env))
        self.assertEqual(row.invoice_status, labels[invoice.status_in_payment])
        invoice.button_draft()
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(row.invoice_status, draft_status)
        self.assertEqual(row.invoice_id, invoice)
        self.assertFalse(order._generate_billing_engine_invoices())

    def test_exact_legacy_rental_invoice_adopted_without_duplicate(self):
        order = self._order(months=1)
        invoice = order._generate_billing_engine_invoices()
        row = order.billing_engine_line_ids
        invoice_line = row.invoice_line_id
        # Emulate a legacy invoice that predates the engine's explicit links.
        row.sudo().write({'invoice_id': False, 'invoice_line_id': False})
        self.assertFalse(row.invoice_id)
        self.assertFalse(order._generate_billing_engine_invoices())
        self.assertEqual(row.invoice_id, invoice)
        self.assertEqual(row.invoice_line_id, invoice_line)
        self.assertEqual(order.invoice_ids, invoice)

    def test_mismatched_legacy_invoice_blocks_duplicate_generation(self):
        for mismatch in ('period', 'amount'):
            with self.subTest(mismatch=mismatch):
                order = self._order(months=1)
                invoice = order._generate_billing_engine_invoices()
                row = order.billing_engine_line_ids
                row.sudo().write({'invoice_id': False, 'invoice_line_id': False})
                if mismatch == 'period':
                    invoice.write({'x_rental_period_end': date(2026, 2, 1)})
                else:
                    invoice.invoice_line_ids.write({'price_unit': 3100000})
                with self.assertRaises(UserError), self.cr.savepoint():
                    order._generate_billing_engine_invoices()
                self.assertEqual(order.invoice_ids, invoice)
                self.assertFalse(row.invoice_id)

    def test_finance_user_generates_with_native_invoice_rights_engine_stays_readonly(self):
        with patch.object(type(self.env['res.partner']), '_avatar_generate_svg', return_value=False):
            finance = new_test_user(
                self.env, login='billing_engine_invoice_finance_user',
                groups='sales_team.group_sale_salesman,account.group_account_invoice',
                company_id=self.company.id,
            )
        order = self._order(months=1, user_id=finance.id)
        invoice = order.with_user(finance)._generate_billing_engine_invoices()
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.create_uid, finance)
        self.assertEqual(invoice.state, 'draft')
        row = order.billing_engine_line_ids.with_user(finance)
        self.assertEqual(row.invoice_id, invoice)
        with self.assertRaises(AccessError):
            row.write({'amount': 1})
        with self.assertRaises(AccessError):
            row.unlink()

    def test_sales_only_user_cannot_generate_invoices_or_create_wizard(self):
        with patch.object(type(self.env['res.partner']), '_avatar_generate_svg', return_value=False):
            salesperson = new_test_user(
                self.env, login='billing_engine_invoice_sales_only_user',
                groups='sales_team.group_sale_salesman', company_id=self.company.id,
            )
        order = self._order(months=1, user_id=salesperson.id)
        with self.assertRaises(AccessError):
            order.with_user(salesperson)._generate_billing_engine_invoices()
        with self.assertRaises(AccessError):
            self.env['rental.billing.engine.invoice.wizard'].with_user(salesperson).create({})
        self.assertFalse(order.invoice_ids)
        self.assertFalse(order.billing_engine_line_ids.invoice_id)


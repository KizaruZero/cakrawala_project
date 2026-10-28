from datetime import date, datetime
from copy import deepcopy
from unittest.mock import patch

from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.x_sale_purchase_custom.models.billing_engine_invoice import LegacyBillingInvoiceMismatch
from .test_billing_engine import TestRentalBillingEngine


@tagged('post_install', '-at_install')
class RentalBillingEngineInvoiceCommon(TransactionCase):
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
        region = cls.env['rpc.wilayah'].create({'name': 'Billing Engine Invoice Test Region'})
        province = cls.env['rpc.provinsi'].create({'name': 'Billing Engine Invoice Test Province', 'wilayah_id': region.id})
        cls.location = cls.env['rpc.kota'].create({'name': 'Billing Engine Invoice Test City', 'provinsi_id': province.id})
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'Billing Engine Invoice Test Pricelist',
            'currency_id': cls.company.currency_id.id,
            'company_id': cls.company.id,
        })
        cls.partner.property_product_pricelist = cls.pricelist
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

@tagged('post_install', '-at_install')
class TestRentalBillingEngineInvoices(RentalBillingEngineInvoiceCommon):

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
        self.assertEqual(january_rows[0].invoice_id.invoice_date, date(2026, 2, 5))
        self.assertEqual(january_rows[-1].invoice_id.invoice_date, date(2026, 2, 16))
        february_rows = self._rows(order).filtered(lambda row: row.period_start == date(2026, 2, 1))
        self.assertEqual(set(february_rows.mapped('invoice_date')), {
            date(2026, 3, 5), date(2026, 3, 16),
        })

    def test_separate_front_every_cycle_uses_original_delivery_day(self):
        order = self._order(grouping_invoice='delivered_date', top_billing='didepan')
        rows = self._rows(order)
        self.assertEqual(rows[0].invoice_date, date(2026, 1, 5))
        self.assertEqual(rows[0].invoice_draft_date, date(2026, 1, 2))
        self.assertEqual(rows[1].invoice_date, date(2026, 2, 5))
        invoices = order._generate_billing_engine_invoices()
        self.assertEqual(set(invoices.mapped('invoice_date')), {
            date(2026, 1, 5), date(2026, 2, 5),
        })

    def test_separate_first_date_weekend_adjustment_then_preparation_lead(self):
        # Actual delivery is Saturday, 10 January 2026; Invoicing Day is ignored.
        order = self._order(
            delivery=date(2026, 1, 10), grouping_invoice='delivered_date',
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

    def test_quarterly_separate_every_cycle_uses_delivery_day_after_period(self):
        order = self._order(
            months=6, delivery=date(2026, 1, 16), invoicing_cycle_period='per_3_months',
            grouping_invoice='delivered_date', top_billing='dibelakang', invoicing_date_monthly='7',
        )
        rows = self._rows(order)
        self.assertEqual(rows[0].rental_end, date(2026, 4, 15))
        self.assertEqual(rows.mapped('invoice_date'), [date(2026, 4, 16), date(2026, 7, 16)])
        self.assertEqual(rows[0].invoice_draft_date, date(2026, 4, 13))
        invoices = order._generate_billing_engine_invoices()
        self.assertEqual(set(invoices.mapped('invoice_date')), {date(2026, 4, 16), date(2026, 7, 16)})
        other_delivery_order = self._order(
            months=6, delivery=date(2026, 1, 5), invoicing_cycle_period='per_3_months',
            grouping_invoice='delivered_date', top_billing='dibelakang', invoicing_date_monthly='7',
        )
        self.assertEqual(self._rows(other_delivery_order).mapped('invoice_date'),
                         [date(2026, 4, 5), date(2026, 7, 5)])

    def test_separate_front_ignores_invoicing_day_in_all_periods(self):
        order = self._order(
            delivery=date(2026, 1, 25), grouping_invoice='delivered_date',
            top_billing='didepan', invoicing_date_monthly='7',
        )
        rows = self._rows(order)
        self.assertEqual(rows[0].invoice_date, date(2026, 1, 25))
        self.assertEqual(rows[1].rental_start, date(2026, 2, 25))
        self.assertEqual(rows[1].invoice_date, date(2026, 2, 25))
        self.assertEqual(rows[1].invoice_draft_date, date(2026, 2, 22))
        invoices = order._generate_billing_engine_invoices(today=date(2026, 2, 1))
        self.assertEqual(set(invoices.mapped('invoice_date')), {
            date(2026, 1, 25), date(2026, 2, 25),
        })

    def test_separate_subsequent_weekend_override_then_preparation_lead(self):
        # February's delivery anniversary is Saturday, 7 February; ignore
        # Invoicing Day = 3, adjust the weekend, then subtract preparation lead.
        order = self._order(
            delivery=date(2026, 1, 7), grouping_invoice='delivered_date',
            top_billing='didepan', invoicing_date_monthly='3',
            weekend_rule_adjustment='next_working_day',
        )
        second = self._rows(order)[1]
        self.assertEqual(second.rental_start, date(2026, 2, 7))
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
        self.assertEqual(first.invoice_date, date(2026, 4, 16))
        self.assertFalse(order._generate_billing_engine_invoices(today=date(2026, 3, 31)))
        invoice = order._generate_billing_engine_invoices(today=date(2026, 4, 1))
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.invoice_date, date(2026, 4, 16))
        self.assertEqual(invoice.amount_untaxed, 9000000)
        self.assertEqual(first.invoice_id, invoice)
        self.assertFalse(second.invoice_id)

    def test_delivery_before_contract_still_uses_original_delivery_day(self):
        order = self._order(
            delivery=date(2025, 12, 16), grouping_invoice='delivered_date',
            top_billing='dibelakang', invoicing_date_monthly='7',
        )
        first, second = self._rows(order)
        self.assertEqual(first.period_start, date(2026, 1, 1))
        self.assertEqual(first.rental_start, date(2026, 1, 16))
        self.assertEqual(first.invoice_date, date(2026, 2, 16))
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

    def test_contract_and_frequency_guard_after_linked_invoice(self):
        order = self._order()
        order._generate_billing_engine_invoices(today=date(2026, 1, 17), due_only=True)
        for values in (
            {'invoicing_cycle_period': 'per_3_months'},
            {'masa_sewa_bulan': 3},
            {'actual_rental_start_date': datetime(2026, 2, 1, 5)},
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
        self.assertIs(generate.call_args.kwargs['due_only'], False)
        self.assertIs(generate.call_args.kwargs['current_month_only'], False)
        self.assertEqual(generate.call_args.kwargs['batch_months'], 6)
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

    def test_mismatched_legacy_invoice_is_skipped_without_duplicate_generation(self):
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
                skipped = []
                self.assertFalse(order._generate_billing_engine_invoices(skip_report=skipped))
                self.assertEqual(len(skipped), 1)
                self.assertEqual(skipped[0]['order_id'], order.id)
                self.assertEqual(skipped[0]['order_name'], order.name)
                self.assertIn('does not match', skipped[0]['reason'])
                self.assertEqual(order.invoice_ids, invoice)
                self.assertFalse(row.invoice_id)
                with self.assertRaises(LegacyBillingInvoiceMismatch), self.cr.savepoint():
                    order._link_existing_billing_engine_invoices()

    def _legacy_mismatch(self, mismatch='amount', **order_values):
        order = self._order(months=1, **order_values)
        invoice = order._generate_billing_engine_invoices(today=date(2026, 1, 17))
        order.billing_engine_line_ids.sudo().write({'invoice_id': False, 'invoice_line_id': False})
        if mismatch == 'period':
            invoice.write({'x_rental_period_end': date(2026, 2, 1)})
        else:
            invoice.invoice_line_ids[-1].write({'price_unit': 3100000})
        return order, invoice

    def test_batch_skips_legacy_conflicts_before_and_after_valid_new_order(self):
        old_first, first_invoice = self._legacy_mismatch('period')
        valid = self._order(months=1)
        old_last, last_invoice = self._legacy_mismatch('amount')
        skipped = []
        invoices = (old_first | valid | old_last)._generate_billing_engine_invoices(
            today=date(2026, 1, 17), skip_report=skipped,
        )
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices, valid.invoice_ids)
        self.assertEqual(invoices.amount_untaxed, 3000000)
        self.assertEqual([item['order_id'] for item in skipped], [old_first.id, old_last.id])
        self.assertEqual(old_first.invoice_ids, first_invoice)
        self.assertEqual(old_last.invoice_ids, last_invoice)
        self.assertFalse((old_first | old_last).billing_engine_line_ids.invoice_id)
        self.assertTrue(valid.billing_engine_line_ids.invoice_id)
        repeated = []
        self.assertFalse((old_first | valid | old_last)._generate_billing_engine_invoices(
            today=date(2026, 1, 17), skip_report=repeated,
        ))
        self.assertEqual(len(repeated), 2)
        self.assertEqual(valid.invoice_ids, invoices)

    def test_partial_legacy_adoption_is_rolled_back_for_skipped_order(self):
        order, invoice = self._legacy_mismatch(order_line=[
            Command.create(self._line_values(date(2026, 1, 5))),
            Command.create(self._line_values(date(2026, 1, 16))),
        ])
        original_values = invoice.read(['state', 'name', 'amount_total', 'invoice_line_ids'])[0]
        skipped = []
        self.assertFalse(order._generate_billing_engine_invoices(
            today=date(2026, 1, 17), skip_report=skipped,
        ))
        self.assertEqual(len(skipped), 1)
        self.assertFalse(order.billing_engine_line_ids.invoice_id)
        self.assertFalse(order.billing_engine_line_ids.invoice_line_id)
        self.assertEqual(invoice.read(['state', 'name', 'amount_total', 'invoice_line_ids'])[0], original_values)

    def test_posted_legacy_invoice_is_not_changed_when_skipped(self):
        order, invoice = self._legacy_mismatch('period')
        invoice.action_post()
        original_values = invoice.read(['state', 'name', 'amount_total', 'invoice_line_ids'])[0]
        skipped = []
        self.assertFalse(order._generate_billing_engine_invoices(
            today=date(2026, 1, 17), skip_report=skipped,
        ))
        self.assertEqual(len(skipped), 1)
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.read(['state', 'name', 'amount_total', 'invoice_line_ids'])[0], original_values)
        self.assertEqual(order.invoice_ids, invoice)

    def test_existing_invoice_outside_engine_is_reported_not_duplicated(self):
        order = self._order(months=1)
        invoice = order._generate_billing_engine_invoices(today=date(2026, 1, 17))
        order.billing_engine_line_ids.sudo().write({'invoice_id': False, 'invoice_line_id': False})
        invoice.write({'x_is_rental_invoice': False})
        skipped = []
        self.assertFalse(order._generate_billing_engine_invoices(
            today=date(2026, 1, 17), skip_report=skipped,
        ))
        self.assertEqual(len(skipped), 1)
        self.assertIn('outside Billing Engine', skipped[0]['reason'])
        self.assertEqual(order.invoice_ids, invoice)

    def test_unrelated_validation_and_access_errors_are_not_skipped(self):
        order = self._order(months=1)
        for error_type in (UserError, AccessError):
            with self.subTest(error_type=error_type):
                skipped = []
                with patch.object(type(order), '_prepare_billing_engine_invoice_line',
                                  side_effect=error_type('Unrelated validation or access failure')):
                    with self.assertRaises(error_type), self.cr.savepoint():
                        order._generate_billing_engine_invoices(
                            today=date(2026, 1, 17), skip_report=skipped,
                        )
                self.assertFalse(skipped)
                self.assertFalse(order.invoice_ids)
                self.assertFalse(order.billing_engine_line_ids.invoice_id)

    def test_wizard_reports_skipped_orders_and_can_open_valid_generated_invoices(self):
        old, original = self._legacy_mismatch()
        valid = self._order(months=1)
        wizard = self.env['rental.billing.engine.invoice.wizard'].create({})
        original_generate = type(self.order_model)._generate_billing_engine_invoices

        def selected_orders(model, **options):
            return original_generate(old | valid, today=date(2026, 1, 17), **options)

        with patch.object(type(self.order_model), '_generate_billing_engine_invoices',
                          autospec=True, side_effect=selected_orders):
            action = wizard.action_generate()
        self.assertEqual(action['res_model'], wizard._name)
        self.assertEqual(action['res_id'], wizard.id)
        self.assertEqual(action['target'], 'new')
        self.assertEqual(action['views'][0][0], self.env.ref(
            'x_sale_purchase_custom.view_billing_engine_invoice_wizard_result_form',
        ).id)
        self.assertEqual(wizard.skipped_order_count, 1)
        self.assertEqual(wizard.generated_invoice_count, 1)
        self.assertIn(old.name, wizard.skipped_orders_report)
        self.assertIn('does not match', wizard.skipped_orders_report)
        self.assertEqual(wizard.generated_invoice_ids, valid.invoice_ids)
        self.assertEqual(old.invoice_ids, original)
        invoice_action = wizard.action_view_generated_invoices()
        self.assertEqual(invoice_action['domain'], [('id', 'in', valid.invoice_ids.ids)])

    def test_wizard_all_skipped_shows_report_without_empty_invoice_action(self):
        old, original = self._legacy_mismatch()
        wizard = self.env['rental.billing.engine.invoice.wizard'].create({})
        original_generate = type(self.order_model)._generate_billing_engine_invoices

        def selected_order(model, **options):
            return original_generate(old, today=date(2026, 1, 17), **options)

        with patch.object(type(self.order_model), '_generate_billing_engine_invoices',
                          autospec=True, side_effect=selected_order):
            action = wizard.action_generate()
        self.assertEqual(action['res_id'], wizard.id)
        self.assertEqual(wizard.skipped_order_count, 1)
        self.assertEqual(wizard.generated_invoice_count, 0)
        self.assertEqual(wizard.action_view_generated_invoices(), {'type': 'ir.actions.act_window_close'})
        self.assertEqual(old.invoice_ids, original)

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

    def test_draft_billing_edits_do_not_use_confirmed_amendment(self):
        order = self._order(state='draft')
        order.write({'top_billing': 'dibelakang'})
        order.write({'top_billing': 'didepan', 'invoicing_date_monthly': '7'})
        self.assertFalse(order.billing_settings_changed)
        order.write({'state': 'sale'})
        self.assertFalse(order.billing_settings_changed)
        self.assertTrue(order.billing_engine_line_ids)

    def test_three_fields_share_one_save_and_wait_for_manual_regeneration(self):
        order = self._order()
        rows = self._rows(order)
        before = rows.read()
        order.write({
            'grouping_invoice': 'delivered_date',
            'invoicing_date_monthly': False,
            'top_billing': 'dibelakang',
        })
        self.assertTrue(order.billing_settings_changed)
        self.assertFalse(order.billing_engine_regenerated)
        order._sync_billing_engine()
        order.action_view_billing_engine()
        self.assertEqual(self._rows(order).ids, rows.ids)
        self.assertEqual(rows.read(), before)
        for values in (
            {'invoicing_date_monthly': '15'}, {'top_billing': 'didepan'},
            {'grouping_invoice': 'all_units'},
        ):
            with self.subTest(values=values), self.assertRaises(UserError), self.cr.savepoint():
                order.with_context(skip_billing_engine_sync=True).write(values)

    def test_identical_values_and_unrelated_saves_do_not_use_amendment(self):
        order = self._order()
        order.write({'invoicing_date_monthly': '20', 'top_billing': 'didepan'})
        order.write({'client_order_ref': 'Unrelated edit'})
        self.assertFalse(order.billing_settings_changed)
        order.write({'invoicing_date_monthly': '7'})
        order.write({'invoicing_date_monthly': '7'})
        self.assertTrue(order.billing_settings_changed)
        self.assertEqual(order.invoicing_date_monthly, '7')

    def test_amendment_limits_cannot_be_reset_by_rpc_or_cancel_to_draft(self):
        order = self._order()
        order.write({'top_billing': 'dibelakang'})
        for field in ('billing_settings_changed', 'billing_engine_regenerated'):
            with self.subTest(field=field), self.assertRaises(UserError), self.cr.savepoint():
                order.sudo().write({field: False})
        order.write({'state': 'cancel'})
        order.write({'state': 'draft'})
        with self.assertRaises(UserError), self.cr.savepoint():
            order.write({'top_billing': 'didepan'})
        with self.assertRaises(UserError), self.cr.savepoint():
            self.order_model.create({'partner_id': self.partner.id, 'billing_engine_regenerated': True})

    def test_regeneration_replaces_all_unbilled_rows_only_once(self):
        order = self._order()
        old_ids = self._rows(order).ids
        order.write({'grouping_invoice': 'delivered_date', 'top_billing': 'dibelakang'})
        action = order.action_generate_billing_engine()
        rows = self._rows(order)
        self.assertEqual(action['res_model'], 'sale.order.billing.engine')
        self.assertTrue(order.billing_engine_regenerated)
        self.assertFalse(set(rows.ids) & set(old_ids))
        self.assertEqual(rows.mapped('invoice_date'), [date(2026, 2, 5), date(2026, 3, 5)])
        self.assertEqual(rows.mapped('billing_revision'), [1, 1])
        self.assertFalse(rows.invoice_id)
        with self.assertRaises(UserError), self.cr.savepoint():
            order.action_generate_billing_engine()
        with self.assertRaises(UserError), self.cr.savepoint():
            order.write({'top_billing': 'didepan'})
        self.assertEqual(self._rows(order).ids, rows.ids)

    def test_regeneration_without_amendment_also_locks_settings(self):
        order = self._order()
        before = self._rows(order).ids
        order.action_generate_billing_engine()
        self.assertFalse(set(self._rows(order).ids) & set(before))
        self.assertFalse(order.billing_settings_changed)
        self.assertTrue(order.billing_engine_regenerated)
        with self.assertRaises(UserError), self.cr.savepoint():
            order.write({'invoicing_date_monthly': '7'})

    def test_regeneration_preserves_billed_rows_and_their_invoices(self):
        order = self._order()
        invoice = order._generate_billing_engine_invoices(today=date(2026, 1, 1))
        first, second = self._rows(order)
        self.assertTrue(first.invoice_id)
        self.assertFalse(second.invoice_id)
        billed_before = first.read()
        invoice_before = invoice.read(['invoice_date', 'state', 'amount_total', 'invoice_line_ids'])
        order.write({
            'grouping_invoice': 'delivered_date', 'invoicing_date_monthly': False,
            'top_billing': 'dibelakang',
        })
        order.action_generate_billing_engine()
        self.assertEqual(first.read(), billed_before)
        self.assertEqual(invoice.read(['invoice_date', 'state', 'amount_total', 'invoice_line_ids']), invoice_before)
        self.assertFalse(second.exists())
        refreshed = self._rows(order)[1]
        self.assertEqual(refreshed.invoice_date, date(2026, 3, 5))
        self.assertEqual(refreshed.billing_revision, 1)
        new_invoice = order._generate_billing_engine_invoices(today=date(2026, 3, 1))
        self.assertEqual(len(new_invoice), 1)
        self.assertNotEqual(invoice, new_invoice)
        self.assertEqual(first.invoice_id, invoice)

    def test_regeneration_keeps_fully_invoiced_schedule(self):
        order = self._order()
        invoices = order._generate_billing_engine_invoices()
        rows = self._rows(order)
        before = rows.read()
        order.write({'top_billing': 'dibelakang'})
        order.action_generate_billing_engine()
        self.assertEqual(self._rows(order).ids, rows.ids)
        self.assertEqual(rows.read(), before)
        self.assertEqual(rows.invoice_id, invoices)
        self.assertFalse(order._generate_billing_engine_invoices())

    def test_pending_amendment_skips_invoice_generation_not_other_orders(self):
        pending = self._order()
        valid = self._order()
        pending.write({'invoicing_date_monthly': '7'})
        skipped = []
        invoices = (pending | valid)._generate_billing_engine_invoices(skip_report=skipped)
        self.assertTrue(invoices)
        self.assertEqual([item['order_id'] for item in skipped], pending.ids)
        self.assertIn('Generate Billing Engine', skipped[0]['reason'])
        self.assertFalse(pending.invoice_ids)
        self.assertFalse(pending._generate_rental_invoices_if_due(date(2026, 1, 31)))
        pending.action_generate_billing_engine()
        self.assertTrue(pending._generate_billing_engine_invoices())

    def test_late_delivery_after_regeneration_does_not_append_to_old_policy_draft(self):
        order = self._order(months=1, order_line=[
            Command.create(self._line_values(date(2026, 1, 20))),
            Command.create(self._line_values(False)),
        ])
        old_invoice = order._generate_billing_engine_invoices()
        self.assertEqual(len(old_invoice), 1)
        old_line_ids = old_invoice.invoice_line_ids.ids
        order.write({'grouping_invoice': 'delivered_date'})
        order.action_generate_billing_engine()
        order.order_line[-1].actual_delivery_date = date(2026, 1, 20)
        new_invoice = order._generate_billing_engine_invoices()
        self.assertEqual(len(new_invoice), 1)
        self.assertNotEqual(old_invoice, new_invoice)
        self.assertEqual(old_invoice.invoice_date, new_invoice.invoice_date)
        self.assertEqual(old_invoice.invoice_line_ids.ids, old_line_ids)
        self.assertEqual(new_invoice.amount_untaxed, 3000000)
        self.assertFalse(order._generate_billing_engine_invoices())

    def test_regeneration_adopts_exact_legacy_invoice_before_deleting_rows(self):
        order = self._order()
        invoice = order._generate_billing_engine_invoices(today=date(2026, 1, 1))
        first, second = self._rows(order)
        first.sudo().write({'invoice_id': False, 'invoice_line_id': False})
        order.write({'top_billing': 'dibelakang'})
        order.action_generate_billing_engine()
        self.assertEqual(first.invoice_id, invoice)
        self.assertTrue(first.exists())
        self.assertFalse(second.exists())

    def test_regeneration_rejects_ambiguous_legacy_invoice_without_deleting_rows(self):
        order = self._order()
        invoice = order._generate_billing_engine_invoices(today=date(2026, 1, 1))
        rows = self._rows(order)
        rows.sudo().write({'invoice_id': False, 'invoice_line_id': False})
        invoice.invoice_line_ids.price_unit = 3100000
        before = rows.read()
        with self.assertRaises(LegacyBillingInvoiceMismatch):
            order.action_generate_billing_engine()
        self.assertEqual(rows.read(), before)
        self.assertFalse(order.billing_engine_regenerated)

    def test_failed_regeneration_rolls_back_deleted_rows_and_allowance(self):
        order = self._order()
        order.write({'top_billing': 'dibelakang'})
        before = self._rows(order).ids
        with patch.object(type(order), '_sync_billing_engine', side_effect=UserError('test rollback')):
            with self.assertRaises(UserError):
                order.action_generate_billing_engine()
        self.assertEqual(self._rows(order).ids, before)
        self.assertFalse(order.billing_engine_regenerated)
        order.action_generate_billing_engine()
        self.assertTrue(order.billing_engine_regenerated)

    def test_invalid_regeneration_inputs_do_not_use_allowance(self):
        for values in ({'start': False, 'delivery': False}, {'masa_sewa_bulan': 0}, {'state': 'draft'}):
            with self.subTest(values=values):
                order = self._order(**values)
                with self.assertRaises(UserError):
                    order.action_generate_billing_engine()
                self.assertFalse(order.billing_engine_regenerated)

    def test_separate_no_invoicing_day_with_custom_cycle(self):
        order = self._order(
            grouping_invoice='delivered_date', invoicing_date_monthly=False,
            billing_period='custom_cycle', top_billing='dibelakang',
        )
        self.assertEqual(self._rows(order).mapped('invoice_date'), [date(2026, 2, 5), date(2026, 3, 5)])
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._order(grouping_invoice='all_units', invoicing_date_monthly=False, billing_period='custom_cycle')

    def test_separate_prorate_uses_delivery_day_not_month_start_or_end(self):
        for top, expected in (
            ('didepan', [date(2026, 1, 16), date(2026, 2, 16), date(2026, 3, 16)]),
            ('dibelakang', [date(2026, 2, 16), date(2026, 3, 16), date(2026, 4, 16)]),
        ):
            with self.subTest(top=top):
                order = self._order(
                    start=datetime(2026, 1, 16, 5), months=2, delivery=date(2026, 1, 16),
                    billing_rule='prorate', grouping_invoice='delivered_date',
                    invoicing_date_monthly=False, top_billing=top,
                )
                self.assertEqual(self._rows(order).mapped('invoice_date'), expected)
                self.assertEqual(self._rows(order)[1].rental_start, date(2026, 2, 1))

    def test_separate_month_end_clamps_then_restores_delivery_day(self):
        order = self._order(
            start=datetime(2028, 1, 31, 5), months=3, delivery=date(2028, 1, 31),
            grouping_invoice='delivered_date', invoicing_date_monthly=False, top_billing='dibelakang',
        )
        self.assertEqual(self._rows(order).mapped('invoice_date'), [
            date(2028, 2, 29), date(2028, 3, 31), date(2028, 4, 30),
        ])

    def test_regeneration_view_and_one_time_field_modifiers(self):
        arch, _view = self.order_model._get_view(
            view_id=self.env.ref('sale.view_order_form').id, view_type='form',
        )
        button = arch.xpath('//header/button[@name="action_generate_billing_engine"]')
        self.assertEqual(len(button), 1)
        self.assertIn('billing_engine_regenerated', button[0].get('invisible'))
        self.assertTrue(button[0].get('confirm'))
        for field in ('grouping_invoice', 'invoicing_date_monthly', 'top_billing'):
            nodes = arch.xpath('//field[@name="%s"]' % field)
            self.assertTrue(nodes)
            for node in nodes:
                self.assertIn('billing_settings_changed', node.get('readonly', ''))
                self.assertIn('billing_engine_regenerated', node.get('readonly', ''))
        day = arch.xpath('//field[@name="invoicing_date_monthly"]')[0]
        self.assertIn("grouping_invoice == 'delivered_date'", day.get('invisible'))

    def test_sales_user_can_regenerate_own_order_but_not_another_users_order(self):
        with patch.object(type(self.env['res.partner']), '_avatar_generate_svg', return_value=False):
            salesperson = new_test_user(
                self.env, login='billing_engine_regeneration_sales_user',
                groups='sales_team.group_sale_salesman', company_id=self.company.id,
            )
        own = self._order(user_id=salesperson.id)
        other = self._order(user_id=self.env.ref('base.user_admin').id)
        own.with_user(salesperson).write({'top_billing': 'dibelakang'})
        own.with_user(salesperson).action_generate_billing_engine()
        self.assertTrue(own.billing_engine_regenerated)
        with self.assertRaises(AccessError):
            other.with_user(salesperson).action_generate_billing_engine()
        self.assertFalse(other.billing_engine_regenerated)

    def test_regeneration_ignores_client_skip_sync_context(self):
        order = self._order()
        before = self._rows(order).ids
        order.with_context(skip_billing_engine_sync=True).action_generate_billing_engine()
        self.assertTrue(order.billing_engine_line_ids)
        self.assertFalse(set(self._rows(order).ids) & set(before))

    def test_copy_is_new_quotation_with_fresh_allowances(self):
        order = self._order()
        order.write({'top_billing': 'dibelakang'})
        order.action_generate_billing_engine()
        copied = order.copy()
        self.assertEqual(copied.state, 'draft')
        self.assertFalse(copied.billing_settings_changed)
        self.assertFalse(copied.billing_engine_regenerated)
        self.assertFalse(copied.billing_engine_line_ids)

    def test_separate_trigger_display_follows_engine_preparation_date(self):
        order = self._order(
            delivery=date(2026, 1, 16), grouping_invoice='delivered_date',
            invoicing_date_monthly=False, top_billing='dibelakang',
        )
        first = self._rows(order)[0]
        self.assertEqual(first.invoice_draft_date, date(2026, 2, 13))
        self.assertEqual(order.order_line.trigger_invoice_print, '13th every month')

    def test_form_allows_three_fields_in_one_save_then_locks_them(self):
        # Use the actual resolved field modifiers with a focused native Form.
        # This also verifies the web save does not send protected flag fields.
        resolved, _view = self.order_model._get_view(
            view_id=self.env.ref('sale.view_order_form').id, view_type='form',
        )
        arch = etree.Element('form')
        for name in ('state', 'is_rental_order', 'billing_settings_changed', 'billing_engine_regenerated'):
            etree.SubElement(arch, 'field', name=name, invisible='1')
        for name in ('grouping_invoice', 'invoicing_date_monthly', 'top_billing'):
            arch.append(deepcopy(resolved.xpath('//field[@name="%s"]' % name)[0]))
        view = self.env['ir.ui.view'].create({
            'name': 'Billing amendment focused form', 'model': 'sale.order',
            'arch': etree.tostring(arch, encoding='unicode'),
        })
        order = self._order()
        with Form(order, view=view) as form:
            form.invoicing_date_monthly = '7'
            form.top_billing = 'dibelakang'
            form.grouping_invoice = 'delivered_date'
            self.assertFalse(order.billing_settings_changed)
        self.assertTrue(order.billing_settings_changed)
        locked = Form(order, view=view)
        with self.assertRaises(AssertionError):
            locked.top_billing = 'didepan'
        with self.assertRaises(AssertionError):
            locked.grouping_invoice = 'all_units'

    def test_combined_setting_and_order_line_save_waits_for_button(self):
        order = self._order()
        before = self._rows(order).read()
        order.write({
            'top_billing': 'dibelakang',
            'order_line': [Command.update(order.order_line.id, {'price_unit': 4000000})],
        })
        self.assertEqual(self._rows(order).read(), before)
        order.action_generate_billing_engine()
        self.assertTrue(all(row.amount == 4000000 for row in self._rows(order)))

    def test_manual_wizard_generates_future_periods_in_six_month_batches(self):
        order = self._order(
            start=datetime(2027, 1, 13, 5), months=36, delivery=date(2027, 1, 13),
            grouping_invoice='delivered_date', invoicing_date_monthly=False,
            top_billing='dibelakang',
        )
        rows = self._rows(order)
        today = date(2026, 10, 15)
        self.assertEqual(len(rows), 36)
        self.assertTrue(all(row.invoice_date > today and row.invoice_draft_date > today for row in rows))
        expected_dates = rows.mapped('invoice_date')
        wizard = self.env['rental.billing.engine.invoice.wizard'].create({})
        with patch.object(fields.Date, 'context_today', return_value=today):
            action = wizard.action_generate()
        invoices = rows.invoice_id
        self.assertEqual(len(invoices), 6)
        self.assertEqual(set(invoices.mapped('state')), {'draft'})
        self.assertEqual(set(invoices.mapped('invoice_date')), set(expected_dates[:6]))
        self.assertEqual(min(invoices.mapped('invoice_date')), date(2027, 2, 13))
        self.assertEqual(max(invoices.mapped('invoice_date')), date(2027, 7, 13))
        self.assertEqual(action['domain'], [('id', 'in', invoices.ids)])
        self.assertTrue(all(row.invoice_line_id.move_id == row.invoice_id for row in rows[:6]))
        self.assertFalse(rows[6:].invoice_id)
        original = invoices.read(['state', 'name', 'invoice_date', 'amount_total', 'invoice_line_ids'])
        for offset in range(6, 36, 6):
            with patch.object(fields.Date, 'context_today', return_value=today):
                action = wizard.action_generate()
            batch = rows[offset:offset + 6].invoice_id
            self.assertEqual(len(batch), 6)
            self.assertFalse(batch & invoices)
            self.assertEqual(action['domain'], [('id', 'in', batch.ids)])
            self.assertEqual(set(batch.mapped('state')), {'draft'})
            self.assertEqual(set(batch.mapped('invoice_date')), set(expected_dates[offset:offset + 6]))
            self.assertFalse(rows[offset + 6:].invoice_id)
        self.assertEqual(invoices.read(['state', 'name', 'invoice_date', 'amount_total', 'invoice_line_ids']), original)
        self.assertEqual(set(rows.invoice_id.mapped('invoice_date')), set(expected_dates))
        self.assertTrue(all(row.invoice_line_id.move_id == row.invoice_id for row in rows))
        with patch.object(fields.Date, 'context_today', return_value=today):
            repeated = wizard.action_generate()
        self.assertEqual(repeated['tag'], 'display_notification')
        self.assertEqual(len(order.invoice_ids), 36)

    def test_six_month_batch_starts_after_one_or_two_existing_invoices(self):
        for existing_count in (1, 2):
            with self.subTest(existing_count=existing_count):
                order = self._order(months=18, top_billing='didepan')
                existing = order._generate_billing_engine_invoices(
                    today=date(2026, existing_count, 1),
                )
                self.assertEqual(len(existing), existing_count)
                existing[:1].action_post()
                before = existing.read(['state', 'name', 'invoice_date', 'amount_total', 'invoice_line_ids'])
                rows = self._rows(order)
                batch = order._generate_billing_engine_invoices(
                    current_month_only=False, batch_months=6,
                )
                self.assertEqual(len(batch), 6)
                self.assertEqual(rows[existing_count:existing_count + 6].invoice_id, batch)
                self.assertFalse(rows[existing_count + 6:].invoice_id)
                self.assertEqual(set(batch.mapped('invoice_date')), {
                    date(2026, month, 20)
                    for month in range(existing_count + 1, existing_count + 7)
                })
                self.assertEqual(existing.read(['state', 'name', 'invoice_date', 'amount_total', 'invoice_line_ids']), before)

    def test_six_month_batch_preserves_frequency_and_never_splits_a_period(self):
        for frequency, count in (
            ('monthly', 6), ('per_3_months', 2), ('per_6_months', 1),
            ('yearly', 1), ('as_duration', 1),
        ):
            with self.subTest(frequency=frequency):
                order = self._order(
                    months=24, invoicing_cycle_period=frequency, top_billing='dibelakang',
                )
                rows = self._rows(order)
                schedule_fields = ['period_start', 'period_end', 'rental_start', 'rental_end',
                                   'invoice_date', 'invoice_draft_date', 'amount', 'total_days']
                schedule = rows.read(schedule_fields)
                batch = order._generate_billing_engine_invoices(
                    current_month_only=False, batch_months=6,
                )
                self.assertEqual(len(batch), count)
                self.assertEqual(rows[:count].invoice_id, batch)
                self.assertFalse(rows[count:].invoice_id)
                self.assertEqual(rows.read(schedule_fields), schedule)
                self.assertEqual(sorted(batch.invoice_line_ids.mapped('price_unit')),
                                 sorted(rows[:count].mapped('amount')))
                self.assertTrue(all(row.invoice_id.x_rental_period_end == row.period_end
                                    for row in rows[:count]))

    def test_six_month_batch_all_units_and_separate_delivery_keep_grouping(self):
        for grouping, count in (('all_units', 6), ('delivered_date', 12)):
            with self.subTest(grouping=grouping):
                order = self._order(months=12, grouping_invoice=grouping, order_line=[
                    Command.create(self._line_values(date(2026, 1, day))) for day in (5, 5, 16)
                ])
                batch = order._generate_billing_engine_invoices(
                    current_month_only=False, batch_months=6,
                )
                self.assertEqual(len(batch), count)
                billed = self._rows(order).filtered('invoice_id')
                self.assertEqual(len(billed), 18)
                self.assertEqual(set(billed.mapped('period_start')), {
                    date(2026, month, 1) for month in range(1, 7)
                })
                self.assertEqual(set(batch.mapped('state')), {'draft'})
                self.assertTrue(all(row.invoice_line_id.move_id == row.invoice_id for row in billed))

    def test_six_month_batch_is_independent_for_each_order_and_clips_to_contract(self):
        short = self._order(months=8)
        future = self._order(start=datetime(2028, 9, 1, 5), months=13, delivery=date(2028, 9, 5))
        wizard = self.env['rental.billing.engine.invoice.wizard'].create({})
        with patch.object(fields.Date, 'context_today', return_value=date(2026, 1, 1)):
            wizard.action_generate()
        self.assertEqual(len(short.invoice_ids), 6)
        self.assertEqual(len(future.invoice_ids), 6)
        wizard.action_generate()
        self.assertEqual(len(short.invoice_ids), 8)
        self.assertEqual(len(future.invoice_ids), 12)
        wizard.action_generate()
        self.assertEqual(len(short.invoice_ids), 8)
        self.assertEqual(len(future.invoice_ids), 13)
        self.assertEqual(wizard.action_generate()['tag'], 'display_notification')

    def test_six_month_batch_fills_earlier_deleted_draft_without_skipping_gaps(self):
        order = self._order(months=18)
        order._generate_billing_engine_invoices(current_month_only=False, batch_months=6)
        rows = self._rows(order)
        untouched = rows.filtered('invoice_id') - rows[2]
        original = untouched.invoice_id.read(['state', 'name', 'invoice_date', 'amount_total', 'invoice_line_ids'])
        rows[2].invoice_id.unlink()
        batch = order._generate_billing_engine_invoices(current_month_only=False, batch_months=6)
        self.assertEqual(len(batch), 3)
        self.assertEqual(set(batch.mapped('x_rental_period_start')), {
            date(2026, 3, 1), date(2026, 7, 1), date(2026, 8, 1),
        })
        self.assertFalse(rows[8:].invoice_id)
        self.assertEqual(untouched.invoice_id.read(['state', 'name', 'invoice_date', 'amount_total', 'invoice_line_ids']), original)

    def test_six_month_batch_adopts_legacy_invoice_before_selecting_its_start(self):
        order = self._order(months=18)
        existing = order._generate_billing_engine_invoices(today=date(2026, 1, 1))
        self.assertEqual(len(existing), 1)
        first = self._rows(order)[0]
        first.sudo().write({'invoice_id': False, 'invoice_line_id': False})
        batch = order._generate_billing_engine_invoices(current_month_only=False, batch_months=6)
        self.assertEqual(first.invoice_id, existing)
        self.assertEqual(len(batch), 6)
        self.assertEqual(set(batch.mapped('x_rental_period_start')), {
            date(2026, month, 1) for month in range(2, 8)
        })
        self.assertFalse(self._rows(order)[7:].invoice_id)

    def test_six_month_batches_preserve_first_and_last_prorated_periods(self):
        order = self._order(
            start=datetime(2026, 10, 14, 5), months=12, delivery=date(2026, 10, 14),
            billing_rule='prorate', grouping_invoice='delivered_date',
            top_billing='dibelakang', invoicing_date_monthly=False,
        )
        rows = self._rows(order)
        self.assertEqual(len(rows), 13)
        schedule_fields = ['rental_start', 'rental_end', 'total_days', 'amount',
                           'invoice_date', 'invoice_draft_date']
        before = rows.read(schedule_fields)
        for expected_count in (6, 6, 1):
            batch = order._generate_billing_engine_invoices(current_month_only=False, batch_months=6)
            self.assertEqual(len(batch), expected_count)
            self.assertEqual(set(batch.mapped('state')), {'draft'})
        self.assertEqual(rows.read(schedule_fields), before)
        self.assertEqual(rows[-1].rental_start, date(2027, 10, 1))
        self.assertEqual(rows[-1].rental_end, date(2027, 10, 13))
        self.assertEqual(rows[-1].total_days, 13)
        self.assertEqual(rows[-1].invoice_line_id.price_unit, rows[-1].amount)
        self.assertFalse(order._generate_billing_engine_invoices(current_month_only=False, batch_months=6))

    def test_cron_due_generation_has_no_manual_six_month_batch_limit(self):
        order = self._order(months=18)
        invoices = order._generate_rental_invoices_if_due(date(2027, 4, 1))
        self.assertEqual(len(invoices), 15)
        self.assertEqual(max(invoices.mapped('invoice_date')), date(2027, 3, 20))
        self.assertFalse(self._rows(order)[15:].invoice_id)

    def test_invalid_invoice_batch_size_rejected_without_invoices(self):
        order = self._order(months=18)
        for invalid in (-1, 1.5, True, '6'):
            with self.subTest(batch_months=invalid):
                with self.assertRaisesRegex(UserError, 'batch size'):
                    order._generate_billing_engine_invoices(current_month_only=False, batch_months=invalid)
        self.assertFalse(order.invoice_ids)

    def test_manual_wizard_keeps_existing_posted_invoice_and_generates_remaining_future_drafts(self):
        order = self._order(months=4, top_billing='didepan')
        posted = order._generate_billing_engine_invoices(today=date(2026, 1, 1))
        self.assertEqual(len(posted), 1)
        posted.action_post()
        before = posted.read(['state', 'name', 'invoice_date', 'amount_total', 'invoice_line_ids'])
        wizard = self.env['rental.billing.engine.invoice.wizard'].create({})
        with patch.object(fields.Date, 'context_today', return_value=date(2026, 1, 1)):
            action = wizard.action_generate()
        new_invoices = self._rows(order).invoice_id - posted
        self.assertEqual(len(new_invoices), 3)
        self.assertEqual(set(new_invoices.mapped('state')), {'draft'})
        self.assertEqual(set(new_invoices.mapped('invoice_date')), {
            date(2026, 2, 20), date(2026, 3, 20), date(2026, 4, 20),
        })
        self.assertEqual(action['domain'], [('id', 'in', new_invoices.ids)])
        self.assertEqual(posted.read(['state', 'name', 'invoice_date', 'amount_total', 'invoice_line_ids']), before)

    def test_rpc_number_excluded_from_engine_invoice_without_changing_order_line(self):
        source_name = 'RPC/2026/10-00033 - %s\nUnit includes maintenance' % self.product.display_name
        order = self._order(months=1, order_line=[Command.create(self._line_values(date(2026, 1, 5), name=source_name))])
        invoice = order._generate_billing_engine_invoices()
        description = invoice.invoice_line_ids.name
        self.assertNotIn('RPC/2026/10-00033', description)
        self.assertIn(self.product.display_name, description)
        self.assertIn('Unit includes maintenance', description)
        self.assertNotIn('Unit plate No:', description)
        self.assertIn('05-01-2026 - 04-02-2026', description)
        self.assertEqual(order.order_line.name, source_name)
        self.assertEqual(invoice.invoice_line_ids.sale_line_ids, order.order_line)
        self.assertEqual(invoice.invoice_line_ids.price_unit, 3000000)
        self.assertEqual(invoice.invoice_line_ids.analytic_distribution, order.order_line.analytic_distribution)

    def test_rpc_only_source_description_falls_back_to_product_name(self):
        for source in ('RPC/2026/10-00033 -', 'RPC/2026/10-00033', 'rpc/2026/10/00033 — '):
            with self.subTest(source=source):
                order = self._order(months=1, order_line=[Command.create(self._line_values(date(2026, 1, 5), name=source))])
                values = order._prepare_billing_engine_invoice_line(self._rows(order)[0])
                self.assertEqual(values['name'].splitlines()[0], self.product.display_name)
                self.assertNotIn('RPC/', values['name'].upper())
                self.assertNotIn('Unit plate No:', values['name'])

    def test_rpc_reference_on_own_line_removed_without_losing_notes(self):
        source_name = '%s\nRPC/2026/10-00033 -\nIncludes annual service' % self.product.display_name
        order = self._order(months=1, order_line=[Command.create(self._line_values(name=source_name))])
        values = order.order_line._prepare_invoice_line()
        self.assertEqual(values['name'], self.product.display_name + '\nIncludes annual service')
        self.assertEqual(order.order_line.name, source_name)

    def test_standard_rental_invoice_preparation_also_excludes_rpc_prefix(self):
        source_name = 'RPC/2026/10-00033 - %s' % self.product.display_name
        order = self._order(months=1, order_line=[Command.create(self._line_values(name=source_name))])
        values = order.order_line._prepare_invoice_line()
        self.assertEqual(values['name'], self.product.display_name)
        self.assertEqual(order.order_line.name, source_name)

    def test_non_rental_invoice_and_non_rpc_descriptions_are_unchanged(self):
        source_name = 'RPC/2026/10-00033 - %s' % self.product.display_name
        normal = self._order(is_rental_order=False, order_line=[Command.create(self._line_values(name=source_name))])
        self.assertIn(source_name, normal.order_line._prepare_invoice_line()['name'])
        notes = '%s\nDriver service - weekends included' % self.product.display_name
        rental = self._order(order_line=[Command.create(self._line_values(name=notes))])
        self.assertEqual(rental.order_line._prepare_invoice_line()['name'], notes)


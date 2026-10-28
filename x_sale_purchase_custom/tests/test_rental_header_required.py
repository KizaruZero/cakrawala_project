from datetime import date, datetime

from lxml import etree

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestRentalRequiredHeader(RentalBillingEngineInvoiceCommon):
    view = 'sale_renting.rental_order_primary_form_view'

    def _quotation(self, **values):
        order = self._order(**{'state': 'draft', 'months': 1, **values})
        order.customer_po_amount = order.amount_total
        return order

    def _assert_quotation_untouched(self, orders):
        self.assertTrue(all(order.state in ('draft', 'sent') for order in orders))
        self.assertFalse(orders.billing_engine_line_ids)
        self.assertFalse(orders.picking_ids)
        self.assertFalse(orders.invoice_ids)

    def test_missing_inputs_block_api_confirmation_and_list_all_fields(self):
        order = self._quotation(
            attention_up='   ', payment_term_id=False, rental_type_id=False,
            location_id=False, invoicing_cycle_period=False,
            invoicing_date_monthly=False, weekend_rule_adjustment=False,
            top_billing=False, billing_rule=False, grouping_invoice=False,
        )
        with self.assertRaises(UserError) as caught:
            order.with_context(skip_rental_header_check=True).action_confirm()
        for label in (
            order.name, 'Attention / UP', 'Payment Terms', 'Rental Type',
            'Location', 'Invoicing Frequency', 'Invoicing Day',
            'Weekend Rule Adjustment', 'TOP', 'Billing Calculation Method', 'Grouping invoice',
        ):
            self.assertIn(label, str(caught.exception))
        self._assert_quotation_untouched(order)

    def test_each_missing_input_is_checked_in_draft_and_sent(self):
        names = (
            'attention_up', 'pricelist_id', 'payment_term_id', 'rental_type_id', 'location_id',
            'rental_start_date', 'rental_return_date', 'invoicing_cycle_period',
            'invoicing_date_monthly', 'weekend_rule_adjustment',
            'top_billing', 'billing_rule', 'grouping_invoice',
        )
        for state in ('draft', 'sent'):
            for name in names:
                with self.subTest(state=state, field=name):
                    order = self._quotation(**{'state': state, name: False})
                    # Order/customer onchange defaults must not disguise an
                    # explicit missing value submitted through the ORM.
                    self.assertFalse(order[name])
                    with self.assertRaisesRegex(UserError, 'Parameter header Rental Order wajib dilengkapi'):
                        order.action_confirm()
                    self._assert_quotation_untouched(order)

    def test_full_header_and_h_zero_confirm_without_actual_rental_dates(self):
        order = self._quotation(
            actual_rental_start_date=False, invoice_print_lead_time=0,
            order_line=[Command.create(self._line_values(actual_delivery_date=False))],
        )
        self.assertFalse(order.actual_rental_start_date)
        self.assertFalse(order.actual_rental_return_date)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertFalse(order.actual_rental_start_date)
        self.assertEqual(len(order.billing_engine_line_ids), 0)
        # Delivery later supplies actual dates through the existing fallback.
        order.order_line.actual_delivery_date = date(2026, 1, 5)
        row = order.billing_engine_line_ids
        self.assertEqual(len(row), 1)
        self.assertEqual(row.invoice_draft_date, row.invoice_date)

    def test_negative_lead_time_blocks_confirmation(self):
        order = self._quotation(invoice_print_lead_time=-1)
        with self.assertRaisesRegex(UserError, 'tidak boleh negatif'):
            order.action_confirm()
        self._assert_quotation_untouched(order)

    def test_separate_delivery_does_not_require_invisible_invoicing_day(self):
        order = self._quotation(grouping_invoice='delivered_date', invoicing_date_monthly=False)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertFalse(order.invoicing_date_monthly)
        self.assertEqual(order.billing_engine_line_ids.invoice_date, date(2026, 1, 5))

    def test_batch_missing_header_stops_every_order_before_po_warning(self):
        valid = self._quotation()
        invalid = self._quotation(top_billing=False)
        valid.customer_po_amount = valid.amount_total + 1
        with self.assertRaises(UserError) as caught:
            (valid | invalid).action_confirm()
        self.assertIn(invalid.name, str(caught.exception))
        self.assertIn('TOP', str(caught.exception))
        self._assert_quotation_untouched(valid | invalid)
        self.assertFalse(self.env['rental.customer.po.price.warning'].search([
            ('order_ids', 'in', (valid | invalid).ids),
        ]))

    def test_po_warning_cannot_bypass_a_subsequently_cleared_header(self):
        order = self._quotation()
        order.customer_po_amount += 1
        action = order.action_confirm()
        wizard = self.env[action['res_model']].browse(action['res_id'])
        order.location_id = False
        with self.assertRaisesRegex(UserError, 'Location'):
            wizard.action_confirm()
        self._assert_quotation_untouched(order)

    def test_form_requires_header_inputs_but_h_zero_can_be_saved(self):
        order = self._quotation(invoice_print_lead_time=0)
        form = Form(order, view=self.view)
        for name in (
            'attention_up', 'pricelist_id', 'payment_term_id', 'rental_type_id', 'location_id',
            'rental_start_date', 'rental_return_date', 'invoicing_cycle_period',
            'weekend_rule_adjustment', 'top_billing', 'billing_rule',
            'grouping_invoice', 'invoicing_date_monthly', 'invoice_print_lead_time',
        ):
            self.assertTrue(form._get_modifier(name, 'required'), name)
        for name in ('actual_rental_start_date', 'actual_rental_return_date', 'duration', 'return_status'):
            self.assertFalse(form._get_modifier(name, 'required'), name)
        form.attention_up = False
        with self.assertRaisesRegex(AssertionError, 'attention_up is a required field'):
            form.save()
        form.attention_up = 'Required Header Form Test'
        form.save()
        self.assertEqual(order.invoice_print_lead_time, 0)
        form.invoicing_date_monthly = False
        form.grouping_invoice = 'delivered_date'
        self.assertFalse(form._get_modifier('invoicing_date_monthly', 'required'))
        self.assertTrue(form._get_modifier('invoicing_date_monthly', 'invisible'))
        form.save()

    def test_rpc_style_partial_drafts_can_be_created_but_not_confirmed(self):
        order = self.order_model.create({
            'partner_id': self.partner.id, 'is_rental_order': True,
            'rental_start_date': datetime(2026, 1, 1),
            'rental_return_date': datetime(2026, 2, 1),
        })
        self.assertEqual(order.state, 'draft')
        with self.assertRaisesRegex(UserError, 'Parameter header Rental Order wajib dilengkapi'):
            order.action_confirm()
        self._assert_quotation_untouched(order)

    def test_ordinary_sales_and_legacy_confirmed_orders_keep_existing_behaviour(self):
        ordinary = self._quotation(
            is_rental_order=False, attention_up=False, payment_term_id=False,
            rental_type_id=False, location_id=False, invoicing_cycle_period=False,
            top_billing=False, billing_rule=False, grouping_invoice=False,
            invoice_print_lead_time=-1,
        )
        form = Form(ordinary, view=self.view)
        self.assertFalse(form._get_modifier('attention_up', 'required'))
        self.assertFalse(form._get_modifier('payment_term_id', 'required'))
        ordinary.action_confirm()
        self.assertEqual(ordinary.state, 'sale')
        legacy = self._order(attention_up=False, location_id=False, invoice_print_lead_time=0)
        legacy.note = 'Historical confirmed data remains editable.'
        legacy._validate_rental_header_for_confirmation()
        self.assertEqual(legacy.state, 'sale')
        form = Form(legacy, view=self.view)
        self.assertFalse(form._get_modifier('attention_up', 'required'))
        self.assertFalse(form._get_modifier('location_id', 'required'))

    def test_no_global_not_null_fields_added_for_old_data_or_non_rental_orders(self):
        for name in (
            'attention_up', 'payment_term_id', 'rental_type_id', 'location_id',
            'invoicing_cycle_period', 'weekend_rule_adjustment',
            'top_billing', 'billing_rule', 'grouping_invoice', 'invoice_print_lead_time',
        ):
            self.assertFalse(self.order_model._fields[name].required, name)
        architecture = etree.fromstring(self.order_model.get_view(
            view_id=self.env.ref(self.view).id, view_type='form',
        )['arch'].encode())
        self.assertTrue(architecture.xpath("//field[@name='attention_up'][@required]"))

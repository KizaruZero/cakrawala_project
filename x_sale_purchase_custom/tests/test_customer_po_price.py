from datetime import date

from lxml import etree, html

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestRentalCustomerPoPrice(RentalBillingEngineInvoiceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.currency_id = cls.env.ref('base.IDR')
        cls.pricelist.currency_id = cls.env.company.currency_id

    def _quotation(self, po_amount=None, **overrides):
        order = self._order(**{'state': 'draft', 'months': 1, **overrides})
        order.customer_po_amount = order.amount_total if po_amount is None else po_amount
        return order

    def _warning(self, orders):
        action = orders.action_confirm()
        self.assertIsInstance(action, dict)
        self.assertEqual(action['res_model'], 'rental.customer.po.price.warning')
        self.assertEqual(action['target'], 'new')
        return self.env[action['res_model']].browse(action['res_id'])

    def _assert_not_confirmed(self, orders):
        self.assertTrue(all(order.state in ('draft', 'sent') for order in orders))
        self.assertFalse(orders.billing_engine_line_ids)
        self.assertFalse(orders.picking_ids)
        self.assertFalse(orders.invoice_ids)

    def test_field_below_customer_po_date_without_draft_required_constraint(self):
        field = self.env['sale.order']._fields['customer_po_amount']
        self.assertEqual(field.type, 'monetary')
        self.assertEqual(field.currency_field, 'currency_id')
        self.assertFalse(field.required)
        self.assertFalse(field.copy)
        self.assertTrue(field.tracking)
        root = etree.fromstring(self.env.ref(
            'x_sale_purchase_custom.sale_order_form_inherit_rental_dates'
        ).arch_db.encode())
        values = root.xpath('//field[@name="customer_po_date"]/following-sibling::*[1]')
        self.assertEqual(values[0].get('name'), 'customer_po_amount')
        self.assertEqual(values[0].get('invisible'), 'not is_rental_order')

    def test_missing_price_allows_saving_but_blocks_confirmation(self):
        order = self._quotation(po_amount=0)
        order.note = 'Quotation can still be saved.'
        with self.assertRaisesRegex(UserError, 'Harga PO Customer wajib diisi'):
            order.action_confirm()
        self._assert_not_confirmed(order)

    def test_sent_negative_and_rounded_zero_prices_are_not_valid(self):
        for amount in (-10000, 0.001):
            with self.subTest(amount=amount):
                order = self._quotation(po_amount=amount, state='sent')
                with self.assertRaisesRegex(UserError, 'Harga PO Customer wajib diisi'):
                    order.action_confirm()
                self._assert_not_confirmed(order)

    def test_matching_total_confirms_and_generates_billing_engine(self):
        order = self._quotation(months=36)
        self.assertNotEqual(order.amount_total, order.x_total_keseluruhan)
        self.assertTrue(order.action_confirm())
        self.assertEqual(order.state, 'sale')
        self.assertEqual(len(order.billing_engine_line_ids), 36)
        self.assertFalse(order.invoice_ids)

    def test_comparison_includes_taxes_and_uses_currency_precision(self):
        group = self.env['account.tax.group'].create({
            'name': 'Customer PO Test PPN', 'country_id': self.company.account_fiscal_country_id.id,
        })
        tax = self.env['account.tax'].create({
            'name': 'Customer PO Test PPN 11%', 'amount': 11,
            'type_tax_use': 'sale', 'tax_group_id': group.id,
        })
        order = self._quotation(order_line=[Command.create(self._line_values(
            date(2026, 1, 5),
            tax_ids=[Command.set(tax.ids)],
        ))])
        self.assertEqual(order.amount_total, 3330000)
        order.customer_po_amount = order.amount_untaxed
        warning = self._warning(order)
        self.assertIn('3,330,000.00', warning.comparison_html)
        self._assert_not_confirmed(order)
        order.customer_po_amount = order.amount_total + 0.001
        self.assertEqual(order.currency_id.compare_amounts(order.customer_po_amount, order.amount_total), 0)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_mismatch_only_opens_warning_and_cancel_preserves_quotation(self):
        order = self._quotation(po_amount=2500000)
        before = order.read(['state', 'amount_total', 'customer_po_amount', 'order_line'])
        warning = self._warning(order)
        root = html.fragment_fromstring(warning.comparison_html, create_parent='div')
        self.assertIn('Harga PO Customer', root.text_content())
        self.assertIn('3,000,000.00', root.text_content())
        self.assertIn('2,500,000.00', root.text_content())
        self.assertIn('500,000.00', root.text_content())
        self.assertEqual(order.read(['state', 'amount_total', 'customer_po_amount', 'order_line']), before)
        self._assert_not_confirmed(order)
        view = etree.fromstring(self.env.ref(
            'x_sale_purchase_custom.view_customer_po_price_warning_form'
        ).arch_db.encode())
        self.assertEqual(view.xpath('//button[@name="action_confirm"]/@string'), ['Tetap Konfirmasi'])
        self.assertEqual(view.xpath('//button[@special="cancel"]/@string'), ['Batal'])
        warning.unlink()  # Cancelling/closing the popup never confirms the SO.
        self._assert_not_confirmed(order)

    def test_accepting_warning_runs_normal_confirmation_without_repricing(self):
        order = self._quotation(po_amount=2500000)
        warning = self._warning(order)
        totals = order.read(['amount_total', 'customer_po_amount'])
        result = warning.action_confirm()
        self.assertEqual(result['type'], 'ir.actions.act_window_close')
        self.assertEqual(order.state, 'sale')
        self.assertEqual(len(order.billing_engine_line_ids), 1)
        self.assertEqual(order.read(['amount_total', 'customer_po_amount']), totals)
        self.assertFalse(order.invoice_ids)
        rows = order.billing_engine_line_ids
        with self.assertRaises(UserError):
            warning.action_confirm()
        self.assertEqual(order.billing_engine_line_ids, rows)

    def test_cleared_po_price_cannot_be_bypassed_using_an_old_warning(self):
        order = self._quotation(po_amount=2500000)
        warning = self._warning(order)
        order.customer_po_amount = 0
        with self.assertRaisesRegex(UserError, 'Harga PO Customer wajib diisi'):
            warning.action_confirm()
        self._assert_not_confirmed(order)

    def test_changed_po_amount_requires_a_fresh_warning(self):
        order = self._quotation(po_amount=2500000)
        warning = self._warning(order)
        order.customer_po_amount = 2600000
        action = warning.action_confirm()
        self.assertEqual(action['res_model'], warning._name)
        self.assertNotEqual(action['res_id'], warning.id)
        self._assert_not_confirmed(order)
        fresh = self.env[warning._name].browse(action['res_id'])
        self.assertIn('2,600,000.00', fresh.comparison_html)
        fresh.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_changed_so_total_requires_a_fresh_warning(self):
        order = self._quotation(po_amount=2500000)
        warning = self._warning(order)
        order.order_line.price_unit = 4000000
        action = warning.action_confirm()
        self.assertEqual(action['res_model'], warning._name)
        self.assertNotEqual(action['res_id'], warning.id)
        self.assertIn('4,000,000.00', self.env[warning._name].browse(action['res_id']).comparison_html)
        self._assert_not_confirmed(order)

    def test_corrected_matching_amount_can_continue_without_another_warning(self):
        order = self._quotation(po_amount=2500000)
        warning = self._warning(order)
        order.customer_po_amount = order.amount_total
        result = warning.action_confirm()
        self.assertEqual(result['type'], 'ir.actions.act_window_close')
        self.assertEqual(order.state, 'sale')

    def test_batch_warning_does_not_partially_confirm_matching_orders(self):
        matching = self._quotation()
        different = self._quotation(po_amount=2500000)
        orders = matching | different
        warning = self._warning(orders)
        self.assertEqual(set(warning.order_ids.ids), set(orders.ids))
        self._assert_not_confirmed(orders)
        warning.action_confirm()
        self.assertEqual(set(orders.mapped('state')), {'sale'})
        self.assertEqual(len(orders.billing_engine_line_ids), 2)

    def test_missing_price_in_batch_blocks_all_orders(self):
        matching = self._quotation()
        missing = self._quotation(po_amount=0)
        with self.assertRaisesRegex(UserError, 'Harga PO Customer wajib diisi'):
            (matching | missing).action_confirm()
        self._assert_not_confirmed(matching | missing)

    def test_fake_skip_flags_and_other_orders_warning_cannot_acknowledge(self):
        order = self._quotation(po_amount=2500000)
        other = self._quotation(po_amount=2500000)
        unrelated = self._warning(other)
        for context in (
            {'skip_customer_po_price_check': True},
            {'_rental_customer_po_warning_id': True},
            {'_rental_customer_po_warning_id': unrelated.id},
        ):
            with self.subTest(context=context):
                self._warning(order.with_context(**context))
                self._assert_not_confirmed(order)
        order.customer_po_amount = 0
        with self.assertRaisesRegex(UserError, 'Harga PO Customer wajib diisi'):
            order.with_context(skip_customer_po_price_check=True).action_confirm()

    def test_warning_respects_transient_owner_and_order_permissions(self):
        alice = new_test_user(self.env, login='po_warning_alice', groups='sales_team.group_sale_salesman')
        bob = new_test_user(self.env, login='po_warning_bob', groups='sales_team.group_sale_salesman')
        order = self._quotation(po_amount=2500000, user_id=alice.id)
        action = order.with_user(alice).action_confirm()
        warning = self.env[action['res_model']].browse(action['res_id'])
        with self.assertRaises(AccessError):
            warning.with_user(bob).action_confirm()
        self._assert_not_confirmed(order)
        warning.with_user(alice).action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_regular_sales_and_existing_confirmed_orders_are_unaffected(self):
        ordinary = self._quotation(po_amount=0, is_rental_order=False)
        self.assertFalse(ordinary.is_rental_order)
        ordinary.action_confirm()
        self.assertEqual(ordinary.state, 'sale')
        legacy = self._order()
        self.assertEqual(legacy.customer_po_amount, 0)
        before = legacy.read(['state', 'amount_total', 'billing_engine_line_ids'])
        legacy.note = 'Legacy confirmed order remains editable without backfilling PO price.'
        self.assertEqual(legacy.read(['state', 'amount_total', 'billing_engine_line_ids']), before)

    def test_duplicate_resets_customer_po_price(self):
        original = self._quotation()
        copied = original.copy()
        self.assertEqual(copied.state, 'draft')
        self.assertEqual(copied.customer_po_amount, 0)
        self.assertEqual(original.customer_po_amount, original.amount_total)


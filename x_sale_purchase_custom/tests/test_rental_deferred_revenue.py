from copy import deepcopy
from datetime import date

from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestRentalDeferredRevenue(RentalBillingEngineInvoiceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.deferred_account = cls.env['account.account'].create({
            'name': 'Rental Deferred Liability QA', 'code': '799990010',
            'account_type': 'liability_current', 'company_ids': [Command.set(cls.company.ids)],
        })
        cls.deferred_journal = cls.env['account.journal'].create({
            'name': 'Rental Deferred Recognition QA', 'code': 'RDRQ', 'type': 'general', 'company_id': cls.company.id,
        })
        cls.deferred_model = cls.env['account.deferred.model'].create({
            'name': 'Pendapatan Diterima Di Muka', 'deferred_type': 'revenue',
            'company_id': cls.company.id, 'method_number': 12, 'method_period': 1,
            'first_recognition': 'next_month', 'deferred_account_id': cls.deferred_account.id,
            'recognition_account_id': cls.income_account.id, 'journal_id': cls.deferred_journal.id,
        })
        cls.company.rental_deferred_revenue_model_id = cls.deferred_model
        cls.Entry = cls.env['account.deferred.entry'].with_context(active_test=False)

    def _rental(self, **values):
        return self._order(top_billing='dibelakang', **values)

    def _entries(self, order):
        return self.Entry.search([('rental_order_id', '=', order.id)]).sorted('rental_sale_line_id')

    def _automatic_account(self):
        self.deferred_account.write({'deferred_model_id': self.deferred_model.id, 'deferred_automation': 'draft'})
        self.product.property_account_income_id = self.deferred_account

    def test_seven_delivered_then_three_remaining_never_duplicate(self):
        order = self._rental(months=36, order_line=[
            Command.create(self._line_values(date(2026, 1, 5) if index < 7 else False,
                           price_unit=4300000, name='RPC/2026/10-00033 - Unit %s' % index))
            for index in range(10)
        ])
        before = order.order_line.read(['name', 'price_unit', 'product_uom_qty', 'discount'])
        self.assertTrue(order.can_create_rental_deferred)
        action = order.action_create_rental_deferred_revenue()
        entries = self._entries(order)
        self.assertEqual(len(entries), 7)
        self.assertEqual(action['res_model'], 'account.deferred.entry')
        self.assertEqual(set(entries.mapped('state')), {'draft'})
        self.assertEqual(set(entries.mapped('original_value')), {154800000})
        self.assertEqual(set(entries.mapped('method_number')), {36})
        self.assertFalse(entries.line_ids.move_id)
        self.assertFalse(order.can_create_rental_deferred)
        last = order.order_line.filtered(lambda line: not line.actual_delivery_date)
        last.actual_delivery_date = date(2026, 1, 16)
        self.assertTrue(order.can_create_rental_deferred)
        order.action_create_rental_deferred_revenue()
        all_entries = self._entries(order)
        self.assertEqual(len(all_entries), 10)
        self.assertEqual(order.rental_deferred_count, 10)
        self.assertEqual(len(all_entries - entries), 3)
        self.assertEqual(set((all_entries - entries).mapped('date')), {date(2026, 1, 16)})
        self.assertEqual(set(order.order_line.mapped('rental_deferred_state')), {'draft'})
        with self.assertRaisesRegex(UserError, 'No new Rental Order lines'):
            order.action_create_rental_deferred_revenue()
        self.assertEqual(order.order_line.read(['name', 'price_unit', 'product_uom_qty', 'discount']), before)

    def test_actual_date_description_analytic_and_model_defaults(self):
        order = self._rental(months=48, delivery=date(2026, 1, 17))
        line = order.order_line
        values = (line.name, deepcopy(line.analytic_distribution), order.amount_total, order.write_date)
        order.action_create_rental_deferred_revenue()
        entry = self._entries(order)
        self.assertEqual(entry.name, '%s - %s' % (line.product_id.with_context(display_default_code=False).display_name, self.unit_account.name))
        self.assertEqual(entry.date, date(2026, 1, 17))
        self.assertEqual(entry.deferred_type, 'revenue')
        self.assertEqual(entry.model_id, self.deferred_model)
        self.assertEqual(entry.method_number, 48)
        self.assertEqual(len(entry.line_ids), 48)
        self.assertEqual(entry.line_ids[:1].date, entry.date)
        self.assertEqual(entry.method_period, self.deferred_model.method_period)
        self.assertEqual(entry.computation, self.deferred_model.computation)
        self.assertEqual(entry.journal_id, self.deferred_journal)
        self.assertEqual(entry.deferred_account_id, self.deferred_account)
        self.assertEqual(entry.recognition_account_id, self.income_account)
        self.assertEqual(entry.analytic_distribution, line.analytic_distribution)
        self.assertEqual(entry.rental_analytic_account_id, self.unit_account)
        self.assertEqual(entry.rental_unit_plate_no, getattr(self.unit_account, 'license_plate', False) or self.unit_account.name)
        self.assertFalse(entry.source_move_id)
        self.assertEqual((line.name, line.analytic_distribution, order.amount_total, order.write_date), values)

    def test_stopped_and_written_off_statuses_follow_the_source_without_duplicate(self):
        for action, state in [('action_stop_deferred', 'stopped'), ('action_write_off_deferred', 'written_off')]:
            order = self._rental(months=36, delivery=date(2026, 1, 17))
            order.action_create_rental_deferred_revenue()
            entry = self._entries(order)
            entry.action_validate()
            self.assertEqual(entry.state, 'running')
            getattr(entry, action)()
            self.assertEqual(order.order_line.rental_deferred_state, state)
            self.assertEqual(order.rental_deferred_count, 1)
            self.assertFalse(order.can_create_rental_deferred)
            with self.assertRaisesRegex(UserError, 'No new Rental Order lines'):
                order.action_create_rental_deferred_revenue()

    def test_new_name_uses_product_and_analytic_not_rpc_quantity_or_period(self):
        order = self._rental(delivery=date(2026, 1, 17))
        line = order.order_line
        line.name = 'RPC/2026/10-0033 - old description 1 unit 17-01-2026 - 16-02-2026'
        self.unit_account.name = 'B 9935 UXJ - FN-2026-001'
        before = line.read(['name', 'price_unit', 'product_uom_qty', 'analytic_distribution'])
        order.action_create_rental_deferred_revenue()
        self.assertEqual(self._entries(order).name, '%s - B 9935 UXJ - FN-2026-001' % self.product.with_context(display_default_code=False).display_name)
        self.assertEqual(line.read(['name', 'price_unit', 'product_uom_qty', 'analytic_distribution']), before)

    def test_original_value_respects_quantity_discount_and_excludes_taxes(self):
        taxes = self.env['account.tax'].create([
            {'name': 'Deferred QA PPN 11%', 'amount': 11, 'type_tax_use': 'sale', 'company_id': self.company.id},
            {'name': 'Deferred QA PPh 2%', 'amount': -2, 'type_tax_use': 'sale', 'company_id': self.company.id},
        ])
        order = self._rental(months=36, order_line=[Command.create(self._line_values(
            price_unit=4300000, product_uom_qty=2, discount=10, tax_ids=[Command.set(taxes.ids)],
        ))])
        before = order.order_line.read(['price_unit', 'discount', 'price_subtotal', 'price_tax', 'price_total'])
        order.action_create_rental_deferred_revenue()
        self.assertEqual(self._entries(order).original_value, 4300000 * 2 * 36 * 0.9)
        self.assertEqual(order.order_line.read(['price_unit', 'discount', 'price_subtotal', 'price_tax', 'price_total']), before)

    def test_included_ppn_is_removed_from_original_value(self):
        tax = self.env['account.tax'].create({
            'name': 'Deferred QA Included PPN', 'amount': 11, 'type_tax_use': 'sale',
            'price_include_override': 'tax_included', 'company_id': self.company.id,
        })
        order = self._rental(months=36, order_line=[Command.create(self._line_values(
            price_unit=4773000, tax_ids=[Command.set(tax.ids)],
        ))])
        order.action_create_rental_deferred_revenue()
        self.assertEqual(self._entries(order).original_value, 154800000)

    def test_didepan_cannot_create_and_existing_invoice_automation_unchanged(self):
        self._automatic_account()
        order = self._order(top_billing='didepan')
        self.assertFalse(order.can_create_rental_deferred)
        with self.assertRaisesRegex(UserError, 'TOP Dibelakang'):
            order.action_create_rental_deferred_revenue()
        invoices = order._generate_billing_engine_invoices(current_month_only=False)
        invoices.action_post()
        self.assertEqual(len(invoices.deferred_entry_ids), len(invoices))
        self.assertFalse(self._entries(order))

    def test_missing_actual_delivery_does_not_create_even_with_estimate_or_qty(self):
        order = self._rental(delivery=False)
        order.order_line.estimated_delivery_date = date(2026, 1, 5)
        order.order_line.qty_delivered = 1
        self.assertFalse(order.can_create_rental_deferred)
        with self.assertRaisesRegex(UserError, 'Actual Delivery Date'):
            order.action_create_rental_deferred_revenue()
        self.assertFalse(self._entries(order))

    def test_quotation_cancelled_and_ordinary_sales_are_rejected(self):
        for values in [{'state': 'draft'}, {'state': 'sent'}, {'state': 'cancel'}, {'is_rental_order': False}]:
            with self.subTest(values=values):
                order = self._rental(**values)
                self.assertFalse(order.can_create_rental_deferred)
                with self.assertRaisesRegex(UserError, 'confirmed Rental Orders'):
                    order.action_create_rental_deferred_revenue()

    def test_automatic_invoice_deferred_is_skipped_when_contract_item_exists(self):
        self._automatic_account()
        order = self._rental()
        order.action_create_rental_deferred_revenue()
        entry = self._entries(order)
        before = entry.read(['original_value', 'date', 'state', 'method_number', 'line_ids'])
        invoices = order._generate_billing_engine_invoices(current_month_only=False)
        invoices.action_post()
        self.assertFalse(invoices.deferred_entry_ids)
        self.assertEqual(self._entries(order), entry)
        self.assertEqual(entry.read(['original_value', 'date', 'state', 'method_number', 'line_ids']), before)
        invoices.action_create_deferred_entries() if len(invoices) == 1 else invoices[:1].action_create_deferred_entries()
        self.assertFalse(invoices.deferred_entry_ids)

    def test_old_invoice_based_deferred_blocks_duplicate_contract_item(self):
        self._automatic_account()
        order = self._rental()
        invoice = order._generate_billing_engine_invoices(current_month_only=False)[:1]
        invoice.action_post()
        old = invoice.deferred_entry_ids
        self.assertTrue(old)
        before = old.read(['original_value', 'state', 'model_id', 'source_move_line_id'])
        with self.assertRaisesRegex(UserError, 'Invoice-based deferred items already exist'):
            order.action_create_rental_deferred_revenue()
        self.assertFalse(self._entries(order))
        self.assertEqual(old.read(['original_value', 'state', 'model_id', 'source_move_line_id']), before)

    def test_contract_item_still_prevents_duplicates_after_top_amendment(self):
        self._automatic_account()
        order = self._rental()
        order.action_create_rental_deferred_revenue()
        entry = self._entries(order)
        order.top_billing = 'didepan'
        # This test targets accounting de-duplication, not Billing Engine's
        # separate one-time policy regeneration/approval workflow.
        order.action_generate_billing_engine()
        invoices = order._generate_billing_engine_invoices(current_month_only=False)
        invoices.action_post()
        self.assertFalse(invoices.deferred_entry_ids)
        self.assertEqual(self._entries(order), entry)

    def test_unique_source_archived_cancelled_and_deleted_draft(self):
        order = self._rental()
        order.action_create_rental_deferred_revenue()
        entry = self._entries(order)
        with self.assertRaises(ValidationError):
            entry.copy({'rental_sale_line_id': order.order_line.id})
        entry.action_cancel()
        entry.action_archive_record()
        self.assertEqual(order.rental_deferred_count, 1)
        self.assertEqual(order.order_line.rental_deferred_state, 'cancelled')
        with self.assertRaisesRegex(UserError, 'No new Rental Order lines'):
            order.action_create_rental_deferred_revenue()
        entry.unlink()
        self.assertEqual(order.order_line.rental_deferred_state, 'not_created')
        order.action_create_rental_deferred_revenue()
        self.assertEqual(len(self._entries(order)), 1)

    def test_copy_order_has_no_deferred_status_or_source_links(self):
        order = self._rental()
        order.action_create_rental_deferred_revenue()
        copied = order.copy()
        self.assertEqual(copied.rental_deferred_count, 0)
        self.assertEqual(set(copied.order_line.mapped('rental_deferred_state')), {'not_created'})

    def test_native_bulk_validation_updates_rental_line_status(self):
        order = self._rental()
        order.action_create_rental_deferred_revenue()
        self._entries(order).action_validate_selected()
        self.assertEqual(order.order_line.rental_deferred_state, 'closed')
        self.assertEqual(self._entries(order).recognized_value, self._entries(order).original_value)

    def test_model_name_fallback_is_company_scoped_and_normalizes_spaces(self):
        self.company.rental_deferred_revenue_model_id = False
        self.deferred_model.name = 'PENDAPATAN DITERIMA DIMUKA'
        order = self._rental()
        order.action_create_rental_deferred_revenue()
        self.assertEqual(self._entries(order).model_id, self.deferred_model)

    def test_ambiguous_missing_wrong_type_and_nonmonthly_model_are_rejected(self):
        self.company.rental_deferred_revenue_model_id = False
        duplicate = self.deferred_model.copy()
        # Native copy() appends a suffix; keep the intended duplicate name.
        duplicate.name = self.deferred_model.name
        order = self._rental()
        with self.assertRaisesRegex(UserError, 'Select the Rental Deferred Revenue Model'):
            order.action_create_rental_deferred_revenue()
        duplicate.active = False
        self.deferred_model.name = 'Unconfigured model'
        with self.assertRaisesRegex(UserError, 'Select the Rental Deferred Revenue Model'):
            order.action_create_rental_deferred_revenue()
        self.company.rental_deferred_revenue_model_id = self.deferred_model
        self.deferred_model.method_period = 3
        with self.assertRaisesRegex(UserError, 'monthly Deferred Model'):
            order.action_create_rental_deferred_revenue()
        self.deferred_model.method_period = 1
        self.deferred_model.active = False
        with self.assertRaisesRegex(UserError, 'active revenue model'):
            order.action_create_rental_deferred_revenue()
        self.assertFalse(self._entries(order))

    def test_zero_value_is_rejected_before_any_partial_creation(self):
        order = self._rental(order_line=[
            Command.create(self._line_values(price_unit=4300000)),
            Command.create(self._line_values(price_unit=0)),
        ])
        with self.assertRaisesRegex(UserError, 'Original Value must be greater'):
            order.action_create_rental_deferred_revenue()
        self.assertFalse(self._entries(order))

    def test_no_sudo_financial_creation_from_sales_user(self):
        order = self._rental()
        user = new_test_user(self.env, login='rental_deferred_sales', groups='sales_team.group_sale_salesman_all_leads', company_id=self.company.id)
        with self.assertRaises(AccessError):
            order.with_user(user).action_create_rental_deferred_revenue()
        self.assertFalse(self._entries(order))

    def test_prorate_and_quarterly_billing_do_not_change_contract_value(self):
        order = self._rental(months=2, delivery=date(2026, 1, 17),
                             billing_rule='prorate', invoicing_cycle_period='per_3_months')
        self.assertNotEqual(sum(order.billing_engine_line_ids.mapped('amount')), 6000000)
        order.action_create_rental_deferred_revenue()
        entry = self._entries(order)
        self.assertEqual(entry.original_value, 6000000)
        self.assertEqual(entry.method_number, 2)
        self.assertEqual(entry.method_period, 1)

    def test_foreign_currency_converts_at_actual_delivery_date(self):
        currency = self.env.ref('base.EUR')
        if currency == self.company.currency_id:
            currency = self.env.ref('base.USD')
        currency.active = True
        self.env['res.currency.rate'].create([
            {'currency_id': self.company.currency_id.id, 'name': '2026-01-01', 'rate': 1, 'company_id': self.company.id},
            {'currency_id': currency.id, 'name': '2026-01-01', 'rate': 2, 'company_id': self.company.id},
            {'currency_id': currency.id, 'name': '2026-10-01', 'rate': 4, 'company_id': self.company.id},
        ])
        pricelist = self.pricelist.copy({'name': 'Deferred Foreign Currency QA', 'currency_id': currency.id})
        order = self._rental(pricelist_id=pricelist.id)
        self.assertEqual(order.currency_id, currency)
        order.action_create_rental_deferred_revenue()
        self.assertEqual(self._entries(order).original_value, 3000000)
        self.assertEqual(self._entries(order).currency_id, self.company.currency_id)

    def test_original_source_is_immutable_and_cannot_be_set_on_didepan(self):
        order = self._rental()
        order.action_create_rental_deferred_revenue()
        with self.assertRaisesRegex(UserError, 'source of an existing deferred'):
            self._entries(order).write({'rental_sale_line_id': False})
        front = self._order(top_billing='didepan')
        values = front.order_line._prepare_rental_deferred_values(self.deferred_model)
        with self.assertRaisesRegex(ValidationError, 'confirmed TOP Dibelakang'):
            self.Entry.create(values)

    def test_new_invoices_use_model_account_without_changing_product_or_amounts(self):
        order = self._rental()
        product_account = self.product.property_account_income_id
        order.action_create_rental_deferred_revenue()
        invoices = order._generate_billing_engine_invoices(current_month_only=False)
        self.assertEqual(invoices.invoice_line_ids.account_id, self.deferred_account)
        self.assertEqual(set(invoices.mapped('amount_untaxed')), {3000000})
        self.assertEqual(self.product.property_account_income_id, product_account)
        invoices.action_post()
        self.assertEqual(invoices.invoice_line_ids.account_id, self.deferred_account)

    def test_existing_drafts_are_aligned_and_posting_rechecks_account(self):
        order = self._rental()
        invoices = order._generate_billing_engine_invoices(current_month_only=False)
        before = invoices.read(['amount_total', 'amount_untaxed', 'amount_tax', 'invoice_date'])
        details = invoices.invoice_line_ids.read(['name', 'quantity', 'price_unit', 'discount', 'tax_ids'])
        self.assertEqual(invoices.invoice_line_ids.account_id, self.income_account)
        order.action_create_rental_deferred_revenue()
        self.assertEqual(invoices.invoice_line_ids.account_id, self.deferred_account)
        self.assertEqual(invoices.read(['amount_total', 'amount_untaxed', 'amount_tax', 'invoice_date']), before)
        self.assertEqual(invoices.invoice_line_ids.read(['name', 'quantity', 'price_unit', 'discount', 'tax_ids']), details)
        invoices.invoice_line_ids.account_id = self.income_account
        invoices.action_post()
        self.assertEqual(invoices.invoice_line_ids.account_id, self.deferred_account)
        self.assertEqual(invoices.read(['amount_total', 'amount_untaxed', 'amount_tax', 'invoice_date']), before)

    def test_posted_income_invoice_requires_review_and_is_not_rewritten(self):
        order = self._rental()
        invoice = order._generate_billing_engine_invoices(current_month_only=False)[:1]
        invoice.action_post()
        before = invoice.line_ids.read(['account_id', 'balance', 'tax_ids', 'name'])
        with self.assertRaisesRegex(UserError, 'Posted rental invoices do not use the Deferred Account'):
            order.action_create_rental_deferred_revenue()
        self.assertEqual(invoice.line_ids.read(['account_id', 'balance', 'tax_ids', 'name']), before)
        self.assertFalse(self._entries(order))

    def test_mixed_managed_unmanaged_invoice_line_is_not_misclassified(self):
        order = self._rental(order_line=[Command.create(self._line_values(date(2026, 1, 5))), Command.create(self._line_values(False))])
        order.action_create_rental_deferred_revenue()
        invoice = order._generate_billing_engine_invoices(current_month_only=False)[:1]
        self.assertTrue(invoice)
        self.assertEqual(len(invoice.invoice_line_ids), 1)
        invoice.invoice_line_ids.sale_line_ids = order.order_line
        self.assertEqual(len(invoice.invoice_line_ids.sale_line_ids), 2)
        with self.assertRaisesRegex(UserError, 'with and without contract-level deferred'):
            invoice.action_post()
        self.assertEqual(invoice.state, 'draft')

    def test_invoicing_role_keeps_ordinary_and_managed_invoice_posting_access(self):
        user = new_test_user(self.env, login='rental_deferred_invoicing', groups='account.group_account_invoice', company_id=self.company.id)
        self.assertFalse(self.Entry.with_user(user).has_access('read'))
        self.deferred_account.write({'deferred_model_id': self.deferred_model.id, 'deferred_automation': 'draft'})
        front = self._order(top_billing='didepan')
        back = self._rental()
        back.action_create_rental_deferred_revenue()
        for order, account in [(front, self.income_account), (back, self.deferred_account)]:
            invoices = order._generate_billing_engine_invoices(current_month_only=False)
            invoices.with_user(user).action_post()
            self.assertEqual(invoices.invoice_line_ids.account_id, account)
        self.assertFalse(front.rental_deferred_count)
        self.assertEqual(back.rental_deferred_count, 1)

    def test_sales_preparation_can_read_only_its_derived_deferred_account(self):
        order = self._rental()
        order.action_create_rental_deferred_revenue()
        user = new_test_user(self.env, login='rental_deferred_prepare_sales', groups='sales_team.group_sale_salesman_all_leads', company_id=self.company.id)
        self.assertFalse(self.Entry.with_user(user).has_access('read'))
        self.assertEqual(order.order_line.with_user(user)._prepare_invoice_line()['account_id'], self.deferred_account.id)

    def test_accounting_administrator_can_create_without_sudo(self):
        order = self._rental()
        user = new_test_user(self.env, login='rental_deferred_finance_creator',
                             groups='account.group_account_manager,sales_team.group_sale_salesman_all_leads',
                             company_id=self.company.id)
        order.with_user(user).action_create_rental_deferred_revenue()
        entry = self._entries(order)
        self.assertEqual(entry.create_uid, user)
        self.assertEqual(entry.state, 'draft')
        self.assertFalse(entry.line_ids.move_id)

    def test_form_buttons_status_and_settings_are_installed(self):
        root = etree.fromstring(self.env['sale.order'].get_view(
            view_id=self.env.ref('sale.view_order_form').id, view_type='form',
        )['arch'])
        self.assertTrue(root.xpath('//button[@name="action_create_rental_deferred_revenue"]'))
        self.assertTrue(root.xpath('//field[@name="order_line"]//list/field[@name="rental_deferred_state"]'))
        self.assertIn('state', self.env['sale.order.line']._fields['rental_deferred_state'].compute)
        settings = self.env.ref('x_sale_purchase_custom.res_config_settings_rental_deferred')
        self.assertIn('rental_deferred_revenue_model_id', settings.arch_db)

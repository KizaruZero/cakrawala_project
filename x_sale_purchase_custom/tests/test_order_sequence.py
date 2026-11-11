from datetime import datetime

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.tools.convert import convert_file

from .test_billing_engine import TestRentalBillingEngine


@tagged('post_install', '-at_install')
class TestRentalOrderSequence(TestRentalBillingEngine):
    def _create_order(self, **values):
        return self.env['sale.order'].create({'partner_id': self.partner.id, **values})

    def _counter(self, sequence):
        sequence.invalidate_recordset(['number_next_actual'])
        return sequence.number_next_actual

    def test_sales_and_rental_use_independent_counters(self):
        sales = self.env.ref('sale.seq_sale_order')
        rental = self.env.ref('x_sale_purchase_custom.seq_rental_order')
        self.assertEqual(sales.prefix, 'SO')
        before_so, before_ro = self._counter(sales), self._counter(rental)
        ro = self._create_order(is_rental_order=True)
        self.assertEqual(ro.name, 'RO' + str(before_ro).zfill(5))
        self.assertEqual(self._counter(sales), before_so)
        so = self._create_order(is_rental_order=False)
        self.assertEqual(so.name, 'SO' + str(before_so).zfill(5))
        self.assertEqual(self._counter(rental), before_ro + 1)

    def test_rental_menu_context_and_explicit_sales_override(self):
        model = self.env['sale.order'].with_context(in_rental_app=True)
        rental = model.create({'partner_id': self.partner.id})
        sale = model.create({'partner_id': self.partner.id, 'is_rental_order': False})
        self.assertTrue(rental.is_rental_order)
        self.assertTrue(rental.name.startswith('RO'))
        self.assertFalse(sale.is_rental_order)
        self.assertTrue(sale.name.startswith('SO'))

    def test_context_default_rental_flag(self):
        order = self.env['sale.order'].with_context(default_is_rental_order=True).create({
            'partner_id': self.partner.id,
        })
        self.assertTrue(order.is_rental_order)
        self.assertTrue(order.name.startswith('RO'))

    def test_mixed_batch_and_input_values_not_mutated(self):
        values = [
            {'partner_id': self.partner.id, 'is_rental_order': True},
            {'partner_id': self.partner.id, 'is_rental_order': False},
            {'partner_id': self.partner.id, 'is_rental_order': True},
        ]
        before = [dict(value) for value in values]
        orders = self.env['sale.order'].create(values)
        self.assertEqual([order.name[:2] for order in orders], ['RO', 'SO', 'RO'])
        self.assertEqual(values, before)
        self.assertEqual(len(set(orders.mapped('name'))), 3)

    def test_explicit_import_names_preserved_without_consuming_counter(self):
        sequence = self.env.ref('x_sale_purchase_custom.seq_rental_order')
        before = self._counter(sequence)
        for name in ('S00129', 'MANUAL/RENT/2026/01', 'RO-LEGACY'):
            order = self._create_order(is_rental_order=True, name=name)
            self.assertEqual(order.name, name)
        self.assertEqual(self._counter(sequence), before)

    def test_new_and_empty_rental_names_get_ro(self):
        for value in ('New', False):
            order = self._create_order(is_rental_order=True, name=value)
            self.assertTrue(order.name.startswith('RO'))

    def test_duplicate_gets_new_number_but_original_stays_unchanged(self):
        original = self._create_order(is_rental_order=True, name='S00067')
        duplicate = original.copy()
        self.assertEqual(original.name, 'S00067')
        self.assertTrue(duplicate.name.startswith('RO'))
        self.assertNotEqual(original.name, duplicate.name)

    def test_confirmation_and_later_edits_do_not_renumber(self):
        order = self._order(months=1, state='draft', customer_po_amount=3000000)
        number = order.name
        self.assertTrue(number.startswith('RO'))
        order.action_confirm()
        order.client_order_ref = 'QA Sequence Customer PO'
        self.assertEqual(order.name, number)
        self.assertEqual(order.state, 'sale')

    def test_existing_sales_reference_not_renamed_when_type_changes(self):
        order = self._create_order(is_rental_order=False, name='S00999')
        order.is_rental_order = True
        self.assertEqual(order.name, 'S00999')

    def test_rental_line_outside_rental_app_does_not_override_order_type(self):
        order = self._create_order(
            rental_start_date=datetime(2026, 11, 11, 5),
            rental_return_date=datetime(2026, 12, 11, 5),
            order_line=[Command.create({
                'product_id': self.product.id, 'is_rental': True,
                'product_uom_qty': 1, 'price_unit': 3000000,
            })],
        )
        self.assertFalse(order.is_rental_order)
        self.assertTrue(order.name.startswith('SO'))

    def test_explicit_sales_flag_and_rental_line_follow_native_final_type(self):
        order = self._create_order(
            is_rental_order=False,
            rental_start_date=datetime(2026, 11, 11, 5),
            rental_return_date=datetime(2026, 12, 11, 5),
            order_line=[Command.create({
                'product_id': self.product.id, 'is_rental': True,
                'product_uom_qty': 1, 'price_unit': 3000000,
            })],
        )
        self.assertTrue(order.name.startswith('RO' if order.is_rental_order else 'SO'))

    def test_rentable_product_is_not_itself_a_rental_order(self):
        order = self._create_order(order_line=[Command.create({
            'product_id': self.product.id, 'is_rental': False,
            'product_uom_qty': 1, 'price_unit': 3000000,
        })])
        self.assertFalse(order.is_rental_order)
        self.assertTrue(order.name.startswith('SO'))

    def test_rental_schedule_context_line_defaults(self):
        order = self.env['sale.order'].with_context(
            in_rental_app=True,
            convert_default_order_line_values=True,
            default_product_id=self.product.id, default_is_rental=True,
        ).create({
            'partner_id': self.partner.id,
            'rental_start_date': datetime(2026, 11, 11, 5),
            'rental_return_date': datetime(2026, 12, 11, 5),
        })
        self.assertTrue(order.is_rental_order)
        self.assertTrue(order.name.startswith('RO'))

    def test_company_specific_sequences(self):
        company = self.env['res.company'].create({
            'name': 'QA Sequence Second Company', 'company_code': 'QAS',
            'currency_id': self.env.company.currency_id.id,
        })
        for code, prefix in [('sale.order', 'SO-B-'), ('sale.order.rental', 'RO-B-')]:
            self.env['ir.sequence'].create({
                'name': 'QA ' + code, 'code': code, 'prefix': prefix,
                'padding': 3, 'company_id': company.id,
            })
        ro = self._create_order(is_rental_order=True, company_id=company.id)
        so = self._create_order(is_rental_order=False, company_id=company.id)
        self.assertEqual(ro.name, 'RO-B-001')
        self.assertEqual(so.name, 'SO-B-001')
        contextual = self.env['sale.order'].with_context(
            default_company_id=company.id, default_is_rental_order=True,
        ).create({'partner_id': self.partner.id})
        self.assertEqual(contextual.company_id, company)
        self.assertEqual(contextual.name, 'RO-B-002')

    def test_backdated_order_date_and_timezone_for_date_range(self):
        self.env['ir.sequence'].create({
            'name': 'QA Rental Date Range', 'code': 'sale.order.rental',
            'prefix': 'RO/%(range_year)s/%(month)s/', 'padding': 3,
            'use_date_range': True, 'company_id': self.env.company.id,
        })
        order = self._create_order(is_rental_order=True, date_order='2024-12-31 20:00:00')
        self.assertEqual(order.name, 'RO/2025/01/001')

    def test_upgrade_keeps_custom_prefixes_and_next_number(self):
        rental = self.env.ref('x_sale_purchase_custom.seq_rental_order')
        rental.prefix = 'RO-CUSTOM-'
        sale = self.env.ref('sale.seq_sale_order')
        sale.prefix = 'SO-CUSTOM-'
        self._create_order(is_rental_order=True)
        next_number = self._counter(rental)
        convert_file(self.env, 'x_sale_purchase_custom', 'data/order_sequence.xml', {}, mode='update')
        self.assertEqual(rental.prefix, 'RO-CUSTOM-')
        self.assertEqual(sale.prefix, 'SO-CUSTOM-')
        self.assertEqual(self._counter(rental), next_number)

    def test_upgrade_normalizes_stock_sales_prefix_without_resetting_counter(self):
        sale = self.env.ref('sale.seq_sale_order')
        sale.prefix = 'S'
        before = self._counter(sale)
        convert_file(self.env, 'x_sale_purchase_custom', 'data/order_sequence.xml', {}, mode='update')
        self.assertEqual(sale.prefix, 'SO')
        self.assertEqual(self._counter(sale), before)

    def test_missing_rental_sequence_does_not_use_sales_counter(self):
        sale = self.env.ref('sale.seq_sale_order')
        before = self._counter(sale)
        self.env.ref('x_sale_purchase_custom.seq_rental_order').active = False
        with self.assertRaises(UserError), self.cr.savepoint():
            self._create_order(is_rental_order=True)
        self.assertEqual(self._counter(sale), before)

    def test_standard_sales_user_can_allocate_both_sequences(self):
        user = new_test_user(self.env, login='sequence_qa_sales', groups='sales_team.group_sale_salesman')
        orders = self.env['sale.order'].with_user(user).create([
            {'partner_id': self.partner.id, 'is_rental_order': True},
            {'partner_id': self.partner.id, 'is_rental_order': False},
        ])
        self.assertTrue(orders[0].name.startswith('RO'))
        self.assertTrue(orders[1].name.startswith('SO'))

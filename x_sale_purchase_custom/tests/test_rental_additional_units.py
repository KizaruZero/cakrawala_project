from datetime import date

from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import Form, tagged
from odoo.tests.common import new_test_user

from .test_billing_engine import TestRentalBillingEngine


@tagged('post_install', '-at_install')
class TestRentalAdditionalUnits(TestRentalBillingEngine):
    """Includes the existing schedule regressions and exercises Add a line."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_product = cls.env['product.product'].create({
            'name': 'PDU QA Additional Unit', 'type': 'consu', 'rent_ok': True,
            'list_price': 9000000, 'taxes_id': [Command.clear()],
        })

    def _additional(self, order, **overrides):
        return self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': self.other_product.id,
            'product_uom_qty': 1, 'tax_ids': [Command.clear()], **overrides,
        })

    def test_add_confirmed_rental_unit_defaults_previous_price(self):
        order = self._order(months=2)
        original = order.order_line
        line = self._additional(order, is_pdu_rc=True)
        self.assertEqual(line.price_unit, original.price_unit)
        self.assertEqual(original.price_unit, 3000000)
        rows = order.billing_engine_line_ids.filtered(lambda row: row.sale_line_id == line)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(rows.mapped('is_pdu_rc')))
        self.assertTrue(all(row.rate_monthly == 3000000 for row in rows))
        self.assertTrue(all(not row.rental_start and row.amount == 0 for row in rows))
        line.actual_delivery_date = date(2026, 9, 25)
        self.assertTrue(all(row.amount == 3000000 for row in rows))

    def test_unsaved_product_onchange_uses_previous_price(self):
        order = self._order(months=1)
        line = self.env['sale.order.line'].new({
            'order_id': order.id, 'product_id': self.other_product.id,
            'product_uom_qty': 1,
        })
        self.assertEqual(line.price_unit, 3000000)
        self.assertEqual(line.technical_price_unit, 9000000)
        line.product_uom_qty = 2
        self.assertEqual(line.price_unit, 3000000)

    def test_confirmed_order_form_can_add_and_tick_line(self):
        order = self._order(months=1)
        with Form(order, view='sale_renting.rental_order_primary_form_view') as form:
            with form.order_line.new() as line:
                line.product_id = self.other_product
                line.is_pdu_rc = True
        added = order.order_line.filtered(lambda line: line.product_id == self.other_product)
        self.assertEqual(len(added), 1)
        self.assertEqual(added.price_unit, 3000000)
        self.assertTrue(added.is_pdu_rc)

    def test_unsaved_sibling_and_zero_manual_price_are_preserved(self):
        order = self._order(months=1)
        with Form(order, view='sale_renting.rental_order_primary_form_view') as form:
            with form.order_line.new() as line:
                line.product_id = self.other_product
                line.price_unit = 5000000
            with form.order_line.new() as line:
                line.product_id = self.other_product
                self.assertEqual(line.price_unit, 5000000)
        self.assertEqual(order.order_line[-2:].mapped('price_unit'), [5000000, 5000000])
        self.assertEqual(self._additional(order, price_unit=0).price_unit, 0)

    def test_actual_confirm_then_add_line(self):
        order = self._order(months=1, state='draft', customer_po_amount=3000000)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertFalse(order.locked)
        self.assertEqual(self._additional(order).price_unit, 3000000)

    def test_skip_sections_notes_and_down_payment(self):
        order = self._order(months=1)
        self.env['sale.order.line'].create([
            {'order_id': order.id, 'display_type': 'line_section', 'name': 'PDU Section'},
            {'order_id': order.id, 'display_type': 'line_note', 'name': 'PDU Note'},
            {'order_id': order.id, 'product_id': self.other_product.id,
             'is_downpayment': True, 'price_unit': 7000000, 'product_uom_qty': 0},
        ])
        self.assertEqual(self._additional(order).price_unit, 3000000)

    def test_predecessor_follows_sequence_not_product_or_highest_id(self):
        order = self._order(months=1)
        order.order_line.sequence = 10
        self._additional(order, sequence=30, price_unit=6000000)
        self.assertEqual(self._additional(order, sequence=20).price_unit, 3000000)
        self.assertEqual(self._additional(order, sequence=40).price_unit, 6000000)

    def test_batch_and_other_order_prices_are_isolated(self):
        first, second = self._order(months=1), self._order(months=1)
        second.order_line.price_unit = 4000000
        lines = self.env['sale.order.line'].create([
            {'order_id': first.id, 'product_id': self.other_product.id, 'price_unit': 5000000},
            {'order_id': first.id, 'product_id': self.other_product.id},
            {'order_id': second.id, 'product_id': self.other_product.id},
        ])
        self.assertEqual(lines.mapped('price_unit'), [5000000, 5000000, 4000000])

    def test_context_default_order_id(self):
        order = self._order(months=1)
        line = self.env['sale.order.line'].with_context(default_order_id=order.id).create({
            'product_id': self.other_product.id,
        })
        self.assertEqual(line.price_unit, 3000000)

    def test_readonly_price_client_payload_keeps_inherited_default(self):
        order = self._order(months=1)
        line = self._additional(order, technical_price_unit=0)
        self.assertEqual(line.price_unit, 3000000)

    def test_zero_price_is_a_valid_predecessor(self):
        order = self._order(months=1)
        order.order_line.price_unit = 0
        self.assertEqual(self._additional(order).price_unit, 0)

    def test_no_predecessor_uses_standard_pricelist(self):
        order = self._order(months=1, order_line=[])
        self.assertEqual(self._additional(order).price_unit, 9000000)

    def test_quotation_and_regular_sale_keep_standard_pricing(self):
        for overrides in ({'state': 'draft'}, {'is_rental_order': False}):
            order = self._order(months=1, **overrides)
            self.assertEqual(self._additional(order).price_unit, 9000000)

    def test_explicit_price_and_input_order_generation_are_preserved(self):
        order = self._order(months=1)
        self.assertEqual(self._additional(order, price_unit=8000000).price_unit, 8000000)
        order.input_line_ids = [Command.create({
            'product_id': self.other_product.id, 'name': 'PDU Input Order',
            'quantity': 2, 'price_unit': 7500000, 'tax_ids': [Command.clear()],
        })]
        order.action_generate_order_lines()
        generated = order.order_line.filtered(lambda line: line.name == 'PDU Input Order')
        self.assertEqual(len(generated), 2)
        self.assertEqual(generated.mapped('price_unit'), [7500000, 7500000])

    def test_existing_line_is_not_repriced_when_quantity_changes(self):
        order = self._order(months=1)
        existing = order.order_line
        self._additional(order, price_unit=7000000)
        existing.product_uom_qty = 2
        self.assertEqual(existing.price_unit, 3000000)
        added = self._additional(order)
        added.product_uom_qty = 2
        self.assertEqual(added.price_unit, 7000000)

    def test_pdu_rc_tracks_source_even_for_linked_invoice_without_rebilling(self):
        order = self._order(months=2)
        rows = order.billing_engine_line_ids
        before = rows.read(['amount', 'rental_start', 'rental_end', 'invoice_date'])
        journal = self.env['account.journal'].create({
            'name': 'PDU QA Customer Journal', 'code': 'PDUQ', 'type': 'sale',
            'company_id': self.env.company.id,
        })
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner.id, 'journal_id': journal.id,
        })
        rows[0].sudo().invoice_id = invoice
        order.order_line.is_pdu_rc = True
        self.assertTrue(all(rows.mapped('is_pdu_rc')))
        self.assertEqual(rows.read(['amount', 'rental_start', 'rental_end', 'invoice_date']), before)
        self.assertEqual(rows[0].invoice_id, invoice)
        order.order_line.is_pdu_rc = False
        self.assertFalse(any(rows.mapped('is_pdu_rc')))

    def test_pdu_rc_visible_on_both_forms_and_billing_columns(self):
        for view_ref in ('sale.view_order_form', 'sale_renting.rental_order_primary_form_view'):
            view = self.env.ref(view_ref)
            arch = etree.fromstring(self.env['sale.order'].get_view(view.id, 'form')['arch'])
            self.assertTrue(arch.xpath("//field[@name='order_line']/list/field[@name='is_pdu_rc']"))
            self.assertTrue(arch.xpath("//field[@name='order_line']/form//field[@name='is_pdu_rc']"))
            self.assertIn('locked', arch.xpath("//field[@name='order_line']")[0].get('readonly', ''))
        for view_ref, kind in [
            ('x_sale_purchase_custom.view_sale_order_billing_engine_list', 'list'),
            ('x_sale_purchase_custom.view_sale_order_billing_engine_form', 'form'),
        ]:
            view = self.env.ref(view_ref)
            arch = etree.fromstring(self.env['sale.order.billing.engine'].get_view(view.id, kind)['arch'])
            self.assertTrue(arch.xpath("//field[@name='is_pdu_rc']"))
        field = self.env['sale.order.billing.engine']._fields['is_pdu_rc']
        self.assertTrue(field.readonly)
        self.assertTrue(field.store)

    def test_salesperson_edits_source_flag_not_billing_mirror(self):
        user = new_test_user(self.env, login='pdu_qa_salesperson', groups='sales_team.group_sale_salesman')
        order = self._order(months=1, user_id=user.id)
        order.order_line.with_user(user).is_pdu_rc = True
        self.assertTrue(order.billing_engine_line_ids.with_user(user).is_pdu_rc)
        with self.assertRaises(AccessError):
            order.billing_engine_line_ids.with_user(user).write({'is_pdu_rc': False})

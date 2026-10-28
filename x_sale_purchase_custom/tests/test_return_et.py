from datetime import date
from unittest.mock import patch

from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged
from odoo.tests.common import new_test_user

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestRentalReturnET(RentalBillingEngineInvoiceCommon):
    """Real delivery/return pickings; ET never also fills ordinary Returned."""

    def _line_values(self, delivery=date(2026, 1, 5), **overrides):
        return super()._line_values(delivery=delivery, **overrides)

    def _delivery(self, order, lines=None):
        lines = lines if lines is not None else order.order_line
        warehouse = order.warehouse_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': warehouse.out_type_id.id,
            'partner_id': order.partner_shipping_id.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': order.partner_shipping_id.property_stock_customer.id,
            'move_ids': [Command.create({
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_uom_qty, 'product_uom': line.product_uom_id.id,
                'sale_line_id': line.id,
                'location_id': warehouse.lot_stock_id.id,
                'location_dest_id': order.partner_shipping_id.property_stock_customer.id,
            }) for line in lines],
        })
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.write({'quantity': move.product_uom_qty, 'picked': True})
        picking.button_validate()
        self.assertEqual(set(picking.mapped('state')), {'done'})
        self.assertEqual(picking.sale_id, order)
        return picking

    def _native_return(self, picking, moves=None, et=False, validate=True):
        moves = moves if moves is not None else picking.move_ids
        wizard = self.env['stock.return.picking'].create({
            'picking_id': picking.id,
            'product_return_moves': [Command.create({
                'product_id': move.product_id.id, 'move_id': move.id, 'quantity': move.quantity,
            }) for move in moves],
        })
        returned = wizard._create_return()
        if et:
            returned.move_ids._mark_rental_return_et()
        if validate:
            self._validate_return(returned)
        return returned

    def _validate_return(self, picking):
        for move in picking.move_ids:
            move.write({'quantity': move.product_uom_qty, 'picked': True})
        picking.button_validate()
        self.assertEqual(set(picking.mapped('state')), {'done'})

    def _wizard(self, order, selected=None):
        action = order.action_request_early_termination()
        self.assertEqual(action['name'], 'Return Picking ET')
        self.assertEqual(action['res_model'], 'rental.return.picking.et')
        model = self.env[action['res_model']].with_context(**action['context'])
        with Form(model, view='x_sale_purchase_custom.view_rental_return_picking_et_form') as form:
            for index in range(len(form.line_ids)):
                with form.line_ids.edit(index) as row:
                    if selected is None or row.sale_line_id in selected:
                        row.quantity = 1
        return form.save()

    def _two_units(self, **overrides):
        return self._order(order_line=[Command.create(self._line_values()) for _ in range(2)], **overrides)

    def test_popup_defaults_filters_lines_and_does_not_request_before_return(self):
        order = self._order(order_line=[Command.create(self._line_values()) for _ in range(4)])
        first, undelivered, normal, et = order.order_line
        delivery = self._delivery(order, first | normal | et)
        self._native_return(delivery, delivery.move_ids.filtered(lambda move: move.sale_line_id == normal))
        self._native_return(delivery, delivery.move_ids.filtered(lambda move: move.sale_line_id == et), et=True)
        self.assertEqual(normal.qty_returned, 1)
        self.assertEqual(et.qty_returned_et, 1)
        action = order.action_request_early_termination()
        with Form(self.env[action['res_model']].with_context(**action['context']),
                  view='x_sale_purchase_custom.view_rental_return_picking_et_form') as form:
            self.assertEqual(len(form.line_ids), 1)
            with form.line_ids.edit(0) as row:
                self.assertEqual(row.sale_line_id, first)
                self.assertEqual(row.quantity, 0)
        self.assertEqual(undelivered.qty_delivered, 0)
        self.assertFalse(order.is_early_termination_requested)
        self.assertEqual(order.et_penalty_amount, 0)

    def test_return_et_uses_native_picking_and_separate_completed_quantity(self):
        order = self._two_units()
        first, second = order.order_line
        delivery = self._delivery(order)
        wizard = self._wizard(order, first)
        action = wizard.action_return_et()
        returned = self.env['stock.picking'].browse(action['res_id'])
        self.assertEqual(returned.return_id, delivery)
        self.assertEqual(returned.sale_id, order)
        self.assertNotEqual(returned.state, 'done')
        self.assertEqual(returned.move_ids.sale_line_id, first)
        self.assertEqual(returned.move_ids.origin_returned_move_id.sale_line_id, first)
        self.assertTrue(all(returned.move_ids.mapped('is_rental_return_et')))
        self.assertEqual(first.qty_returned_et, 0)
        self.assertEqual(first.qty_returned, 0)
        self.assertTrue(order.is_early_termination_requested)
        self.assertEqual(order.et_return_line_ids, first)
        self.assertEqual(order.et_return_picking_ids, returned)
        self.assertEqual(order.et_penalty_amount, 1500000)
        self._validate_return(returned)
        self.assertEqual(first.qty_returned_et, 1)
        self.assertEqual(first.qty_returned, 0)
        self.assertEqual(first.qty_delivered, 1)
        self.assertEqual(set(self._rows(order).filtered(lambda row: row.sale_line_id == first).mapped('unit_status')), {'return_et'})
        self.assertTrue(order.show_return_button)
        self._native_return(delivery, delivery.move_ids.filtered(lambda move: move.sale_line_id == second))
        self.assertEqual(second.qty_returned, 1)
        self.assertEqual(second.qty_returned_et, 0)
        self.assertEqual(set(self._rows(order).filtered(lambda row: row.sale_line_id == second).mapped('unit_status')), {'returned'})
        self.assertFalse(order.show_return_button)
        self.assertEqual(order.return_status, 'fully_returned')

    def test_one_popup_handles_units_from_multiple_deliveries(self):
        order = self._two_units()
        first, second = order.order_line
        deliveries = self._delivery(order, first) | self._delivery(order, second)
        action = self._wizard(order).action_return_et()
        returned = order.et_return_picking_ids
        self.assertEqual(len(returned), 2)
        self.assertEqual(set(returned.return_id.ids), set(deliveries.ids))
        self.assertEqual(action['domain'], [('id', 'in', returned.ids)])
        self._validate_return(returned)
        self.assertEqual(order.order_line.mapped('qty_returned_et'), [1, 1])
        self.assertEqual(order.order_line.mapped('qty_returned'), [0, 0])

    def test_serial_unit_plate_and_original_lot_are_preserved(self):
        self.product.write({'is_storable': True, 'tracking': 'serial'})
        self.unit_account.name = 'B 1234 AB'
        order = self._order()
        lot = self.env['stock.lot'].create({
            'name': 'RETURN-ET-SERIAL-001', 'product_id': self.product.id,
            'company_id': self.company.id,
        })
        self.env['stock.quant']._update_available_quantity(
            self.product, order.warehouse_id.lot_stock_id, 1, lot_id=lot,
        )
        delivery = self._delivery(order)
        self.assertEqual(delivery.move_line_ids.lot_id, lot)
        wizard = self._wizard(order)
        self.assertEqual(wizard.line_ids.license_plate, 'B 1234 AB')
        action = wizard.action_return_et()
        returned = self.env['stock.picking'].browse(action['res_id'])
        self.assertEqual(returned.move_ids.origin_returned_move_id, delivery.move_ids)
        self.assertEqual(returned.move_line_ids.lot_id, lot)
        self._validate_return(returned)
        self.assertEqual(order.order_line.qty_returned_et, 1)
        self.assertEqual(order.order_line.qty_returned, 0)

    def _settle(self, invoice, amount):
        clearing = self.env['account.account'].create({
            'name': 'ET Payment Clearing', 'code': '799998' + str(invoice.id),
            'account_type': 'asset_current', 'company_ids': [Command.set(self.company.ids)],
        })
        journal = self.env['account.journal'].create({
            'name': 'ET Payment Test', 'code': 'E' + str(invoice.id),
            'type': 'general', 'company_id': self.company.id,
        })
        payment = self.env['account.move'].create({
            'journal_id': journal.id, 'date': invoice.invoice_date,
            'line_ids': [Command.create({
                'account_id': clearing.id, 'partner_id': self.partner.id, 'debit': amount,
            }), Command.create({
                'account_id': self.receivable_account.id, 'partner_id': self.partner.id, 'credit': amount,
            })],
        })
        payment.action_post()
        (invoice.line_ids | payment.line_ids).filtered(
            lambda line: line.account_id == self.receivable_account,
        ).reconcile()

    def test_penalty_only_selected_unit_uninvoiced_draft_not_paid_not_other_units(self):
        # Same product and even the same plate: sale-line identity prevents
        # charging the other unit from a grouped customer invoice.
        order = self._two_units(months=6)
        selected = order.order_line[:1]
        self._delivery(order)
        invoices = order._generate_billing_engine_invoices(current_month_only=False).sorted('invoice_date')
        invoices[1:4].action_post()
        self._settle(invoices[2], invoices[2].amount_total)
        self._settle(invoices[3], invoices[3].amount_total / 2)
        self.assertEqual(invoices[1].payment_state, 'not_paid')
        self.assertEqual(invoices[2].payment_state, 'paid')
        self.assertEqual(invoices[3].payment_state, 'partial')
        invoices[4].button_cancel()
        invoices[5].unlink()
        snapshot = invoices[:5].read(['state', 'invoice_date', 'amount_total', 'amount_residual'])
        self._wizard(order, selected).action_return_et()
        self.assertEqual(order.et_penalty_amount, 2250000)
        self.assertEqual(order.et_return_line_ids, selected)
        self.assertEqual(invoices[:5].read(['state', 'invoice_date', 'amount_total', 'amount_residual']), snapshot)

    def test_penalty_includes_future_uninvoiced_beyond_six_month_invoice_batch(self):
        order = self._order(months=18)
        self._delivery(order)
        order._generate_billing_engine_invoices(current_month_only=False, batch_months=6)
        self.assertEqual(len(order.invoice_ids), 6)
        self._wizard(order).action_return_et()
        self.assertEqual(order.et_penalty_amount, 13500000)
        self.assertEqual(len(order.invoice_ids), 6)

    def test_zero_penalty_replaces_stale_value_when_all_selected_invoices_paid(self):
        order = self._order(months=1, et_penalty_amount=999999)
        self._delivery(order)
        invoice = order._generate_billing_engine_invoices(current_month_only=False)
        invoice.action_post()
        self._settle(invoice, invoice.amount_total)
        self._wizard(order).action_return_et()
        self.assertEqual(order.et_penalty_amount, 0)

    def test_invalid_quantities_are_atomic_and_do_not_create_pickings_or_requests(self):
        order = self._order()
        self._delivery(order)
        wizard = self._wizard(order)
        before = order.picking_ids
        for quantity in (0, -1, 2):
            wizard.line_ids.quantity = quantity
            with self.assertRaises(UserError):
                wizard.action_return_et()
            self.assertEqual(order.picking_ids, before)
            self.assertFalse(order.is_early_termination_requested)

    def test_pending_standard_return_reserves_quantity_and_cancellation_releases_it(self):
        order = self._order()
        delivery = self._delivery(order)
        pending = self._native_return(delivery, validate=False)
        wizard = self._wizard(order)
        with self.assertRaisesRegex(UserError, 'exceeds'):
            wizard.action_return_et()
        pending.action_cancel()
        wizard.action_return_et()
        self.assertTrue(order.is_early_termination_requested)

    def test_repeated_et_submission_is_rejected_without_duplicate_pickings(self):
        order = self._order()
        self._delivery(order)
        wizard = self._wizard(order)
        wizard.action_return_et()
        before = order.picking_ids
        with self.assertRaisesRegex(UserError, 'already been requested'):
            wizard.action_return_et()
        self.assertEqual(order.picking_ids, before)

    def test_legacy_pending_request_without_et_picking_can_use_new_flow(self):
        order = self._order(
            is_early_termination_requested=True, et_penalty_amount=999999,
            et_reason='Legacy pending ET reason',
        )
        self._delivery(order)
        wizard = self._wizard(order)
        self.assertEqual(order.et_penalty_amount, 999999)
        self.assertFalse(order.et_return_picking_ids)
        wizard.action_return_et()
        self.assertEqual(order.et_penalty_amount, 1500000)
        self.assertEqual(order.et_reason, 'Legacy pending ET reason')
        self.assertTrue(order.et_return_picking_ids)

    def test_legacy_approved_request_cannot_be_reopened_or_repriced(self):
        order = self._order(
            is_early_termination_requested=True, et_is_approved=True,
            et_penalty_amount=999999,
        )
        self._delivery(order)
        with self.assertRaisesRegex(UserError, 'already been requested'):
            order.action_request_early_termination()
        self.assertEqual(order.et_penalty_amount, 999999)
        self.assertFalse(order.et_return_picking_ids)

    def test_partial_et_return_backorder_keeps_et_classification(self):
        order = self._order(order_line=[Command.create(self._line_values(product_uom_qty=2))])
        self._delivery(order)
        wizard = self._wizard(order)
        wizard.line_ids.quantity = 2
        action = wizard.action_return_et()
        returned = self.env['stock.picking'].browse(action['res_id'])
        returned.move_ids.write({'quantity': 1, 'picked': True})
        returned.with_context(skip_backorder=True).button_validate()
        self.assertEqual(returned.state, 'done')
        self.assertEqual(order.order_line.qty_returned_et, 1)
        self.assertEqual(order.order_line.qty_returned, 0)
        backorder = returned.backorder_ids
        self.assertEqual(len(backorder), 1)
        self.assertTrue(all(backorder.move_ids.mapped('is_rental_return_et')))
        self._validate_return(backorder)
        self.assertEqual(order.order_line.qty_returned_et, 2)
        self.assertEqual(order.order_line.qty_returned, 0)

    def test_other_order_unit_and_duplicate_lines_cannot_be_submitted(self):
        order, other = self._order(), self._order()
        self._delivery(order)
        self._delivery(other)
        wizard = self._wizard(order)
        source = wizard.line_ids.sale_line_id
        wizard.line_ids.sale_line_id = other.order_line
        with self.assertRaisesRegex(UserError, 'from this Rental Order'):
            wizard.action_return_et()
        wizard.line_ids.sale_line_id = source
        self.env['rental.return.picking.et.line'].create({
            'wizard_id': wizard.id, 'sale_line_id': source.id, 'quantity': 1,
        })
        with self.assertRaisesRegex(UserError, 'selected once'):
            wizard.action_return_et()
        self.assertFalse(order.is_early_termination_requested)

    def test_failed_second_delivery_rolls_back_first_return(self):
        order = self._two_units()
        self._delivery(order, order.order_line[:1])
        self._delivery(order, order.order_line[1:])
        wizard = self._wizard(order)
        before = order.picking_ids
        model = type(self.env['stock.return.picking'])
        original = model._create_return
        called = []

        def fail_second(native):
            called.append(native.picking_id.id)
            if len(called) == 2:
                raise UserError('Native return failure')
            return original(native)

        with patch.object(model, '_create_return', fail_second):
            with self.assertRaisesRegex(UserError, 'Native return failure'):
                wizard.action_return_et()
        self.assertEqual(order.picking_ids, before)
        self.assertFalse(order.is_early_termination_requested)

    def test_pending_et_unit_is_excluded_from_standard_return_popup(self):
        order = self._two_units()
        delivery = self._delivery(order)
        self._wizard(order, order.order_line[:1]).action_return_et()
        native = self.env['stock.return.picking'].create({'picking_id': delivery.id})
        self.assertEqual(native.product_return_moves.move_id.sale_line_id, order.order_line[1:])

    def test_standard_return_opened_before_et_cannot_return_et_unit_again(self):
        order = self._two_units()
        delivery = self._delivery(order)
        move = delivery.move_ids.filtered(lambda item: item.sale_line_id == order.order_line[:1])
        stale = self.env['stock.return.picking'].create({
            'picking_id': delivery.id,
            'product_return_moves': [Command.create({
                'product_id': self.product.id, 'move_id': move.id, 'quantity': 1,
            })],
        })
        self._wizard(order, order.order_line[:1]).action_return_et()
        before = order.picking_ids
        with self.assertRaisesRegex(UserError, 'already has a Return ET'):
            stale.action_create_returns()
        self.assertEqual(order.picking_ids, before)

    def test_unit_status_precedence_and_not_yet_delivered(self):
        order = self._two_units()
        self.assertFalse(any(self._rows(order).mapped('unit_status')))
        self._delivery(order, order.order_line[:1])
        self.assertEqual(self._rows(order).filtered(lambda row: row.sale_line_id == order.order_line[:1]).mapped('unit_status'), ['delivered', 'delivered'])

    def test_popup_and_views_and_returned_et_field_type(self):
        model = self.env['sale.order.line']
        self.assertEqual(model._fields['qty_returned_et'].type, model._fields['qty_returned'].type)
        view = self.env.ref('x_sale_purchase_custom.view_rental_return_picking_et_form')
        root = etree.fromstring(view.arch_db.encode())
        self.assertEqual(root.xpath('//footer/button/@string'), ['Return ET', 'Discard'])
        ro_view = self.env.ref('x_sale_purchase_custom.sale_order_form_inherit_rental_purchase')
        root = etree.fromstring(ro_view.arch_db.encode())
        self.assertFalse(root.xpath('//xpath[@expr="//header"]/button[@name="action_approve_early_termination"]'))
        self.assertTrue(root.xpath('//page[@name="early_termination"]//button[@name="action_approve_early_termination"]'))

    def test_stock_permissions_and_move_classification_cannot_be_forged(self):
        order = self._order()
        delivery = self._delivery(order)
        with self.assertRaisesRegex(UserError, 'classification'):
            delivery.move_ids.write({'is_rental_return_et': True})
        with self.assertRaisesRegex(UserError, 'classification'):
            self.env['stock.move'].create({'is_rental_return_et': True})
        with patch.object(type(self.env['res.partner']), '_avatar_generate_svg', return_value=False):
            user = new_test_user(self.env, login='et_no_stock', groups='sales_team.group_sale_salesman')
        with self.assertRaises(AccessError):
            self.env['rental.return.picking.et'].with_user(user).create({'order_id': order.id})

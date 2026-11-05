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
        self.assertEqual(order.et_status, 'fully_returned')

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
        with self.assertRaisesRegex(UserError, 'not-yet-returned'):
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
        self.assertEqual(order.et_line_ids.reason, 'Legacy pending ET reason')
        self.assertTrue(order.et_return_picking_ids)

    def test_multiple_et_lines_split_approve_warning_popup_and_create_invoice(self):
        from ..wizard.et_create_invoice_warning import STOP_DEFERRED_WARNING_MESSAGE

        order = self._two_units()
        first, second = order.order_line
        self._delivery(order)

        # 1st Request ET for unit 1
        self._wizard(order, first).action_return_et()
        self.assertEqual(len(order.et_line_ids), 1)
        et_line_1 = order.et_line_ids[0]
        self.assertEqual(et_line_1.name, 'ET-01')
        self.assertEqual(et_line_1.sale_line_ids, first)
        self.assertEqual(et_line_1.state, 'pending')
        self.assertEqual(et_line_1.penalty_amount, 1500000)
        self.assertFalse(et_line_1.invoice_id)

        # Cannot Create Invoice before Approve
        with self.assertRaisesRegex(UserError, 'Approve'):
            et_line_1.action_open_create_invoice_warning()

        # Approve ET-01 -> sets state to 'approved', does NOT auto-create invoice
        et_line_1.action_approve()
        self.assertEqual(et_line_1.state, 'approved')
        self.assertFalse(et_line_1.invoice_id)

        # Click Create Invoice -> opens warning popup with exact message
        warn_action = et_line_1.action_open_create_invoice_warning()
        self.assertEqual(warn_action['res_model'], 'et.create.invoice.warning.wizard')
        self.assertEqual(warn_action['target'], 'new')
        warn_wizard = self.env['et.create.invoice.warning.wizard'].browse(warn_action['res_id'])
        self.assertEqual(warn_wizard.warning_message, STOP_DEFERRED_WARNING_MESSAGE)

        # Confirm Create Invoice from warning popup -> generates Draft Penalty Invoice
        inv_action = warn_wizard.action_confirm_create_invoice()
        self.assertEqual(inv_action['res_model'], 'account.move')
        self.assertEqual(et_line_1.state, 'invoiced')
        self.assertTrue(et_line_1.invoice_id)
        self.assertTrue(et_line_1.invoice_id.is_et_penalty_invoice)
        self.assertEqual(et_line_1.invoice_id.state, 'draft')
        self.assertEqual(et_line_1.invoice_id.amount_untaxed, 1500000)

        # 2nd Request ET on the SAME Rental Order for unit 2 -> creates ET-02 without overwriting ET-01
        action_2 = order.action_request_early_termination()
        with Form(self.env[action_2['res_model']].with_context(**action_2['context']),
                  view='x_sale_purchase_custom.view_rental_return_picking_et_form') as form:
            self.assertEqual(len(form.line_ids), 1)
            with form.line_ids.edit(0) as row:
                self.assertEqual(row.sale_line_id, second)
                row.quantity = 1
            wiz_2 = form.save()
        wiz_2.action_return_et()

        self.assertEqual(len(order.et_line_ids), 2)
        et_line_2 = order.et_line_ids[1]
        self.assertEqual(et_line_2.name, 'ET-02')
        self.assertEqual(et_line_2.sale_line_ids, second)
        self.assertEqual(et_line_2.state, 'pending')
        self.assertEqual(et_line_1.state, 'invoiced')

        # Approve & Invoice ET-02 independently
        et_line_2.penalty_amount = 1750000
        et_line_2.action_approve()
        self.assertEqual(et_line_2.state, 'approved')
        self.assertFalse(et_line_2.invoice_id)
        warn_action_2 = et_line_2.action_open_create_invoice_warning()
        warn_wizard_2 = self.env['et.create.invoice.warning.wizard'].browse(warn_action_2['res_id'])
        warn_wizard_2.action_confirm_create_invoice()
        self.assertEqual(et_line_2.state, 'invoiced')
        self.assertNotEqual(et_line_1.invoice_id, et_line_2.invoice_id)
        self.assertEqual(et_line_2.invoice_id.amount_untaxed, 1750000)

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
        req_et_btn = root.xpath('//xpath[@expr="//header"]/button[@name="action_request_early_termination"]')
        self.assertTrue(req_et_btn)
        self.assertEqual(req_et_btn[0].get('invisible'), "not is_rental_order or state not in ('sale', 'done')")
        self.assertTrue(root.xpath('//page[@name="early_termination"]//field[@name="et_line_ids"]//button[@name="action_approve"]'))
        self.assertTrue(root.xpath('//page[@name="early_termination"]//field[@name="et_line_ids"]//button[@name="action_open_create_invoice_warning"]'))
        warn_view = self.env.ref('x_sale_purchase_custom.view_et_create_invoice_warning_wizard_form')
        self.assertIn(
            'Untuk unit yang dilakukan early termination jangan lupa untuk melakukan step stop deferred pada STNK dan Asuransi terkait unit tersebut',
            warn_view.arch_db,
        )

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

    def test_return_status_counts_every_unit_and_et_status_only_the_et_units(self):
        # 1. Normal return flow: all units returned when period ends -> 'fully_returned'
        normal_order = self._two_units()
        n_first, n_second = normal_order.order_line
        n_del = self._delivery(normal_order, n_first) | self._delivery(normal_order, n_second)
        self.assertEqual(normal_order.return_status, 'not_returned')

        # Partial normal return -> 'partial'
        self._native_return(n_del[0], n_del[0].move_ids)
        self.assertEqual(n_first.qty_returned, 1)
        self.assertEqual(n_second.qty_returned, 0)
        self.assertEqual(normal_order.return_status, 'partial')

        # Full normal return -> 'fully_returned'
        self._native_return(n_del[1], n_del[1].move_ids)
        self.assertEqual(n_first.qty_returned, 1)
        self.assertEqual(n_second.qty_returned, 1)
        self.assertEqual(normal_order.return_status, 'fully_returned')
        self.assertEqual(normal_order.et_status, 'not_et')

        # 2. Early Termination: the unit still out keeps Return Status partial, ET is complete on its own unit
        et_order = self._two_units()
        e_first, e_second = et_order.order_line
        self._delivery(et_order, e_first) | self._delivery(et_order, e_second)
        self.assertEqual(et_order.return_status, 'not_returned')

        action = self._wizard(et_order, e_first).action_return_et()
        et_picking = self.env['stock.picking'].browse(action['res_id'])
        self.assertEqual(et_order.et_status, 'requested')
        self.assertEqual(et_order.return_status, 'not_returned')
        self._validate_return(et_picking)
        self.assertEqual(e_first.qty_returned_et, 1)
        self.assertEqual(e_second.qty_returned_et, 0)
        self.assertEqual(et_order.return_status, 'partial')
        self.assertEqual(et_order.et_status, 'fully_returned')

        action2 = self._wizard(et_order, e_second).action_return_et()
        et_picking2 = self.env['stock.picking'].browse(action2['res_id'])
        self.assertEqual(et_order.et_status, 'partially_returned')
        self._validate_return(et_picking2)
        self.assertEqual(e_first.qty_returned_et, 1)
        self.assertEqual(e_second.qty_returned_et, 1)
        self.assertEqual(et_order.return_status, 'fully_returned')
        self.assertEqual(et_order.et_status, 'fully_returned')

    def test_validating_a_return_leaves_the_return_date_for_submit_in(self):
        order = self._two_units()
        normal, et = order.order_line
        delivery = self._delivery(order, normal)
        self._delivery(order, et)
        self._native_return(delivery)
        self.assertEqual(normal.qty_returned, 1)
        self.assertFalse(normal.bastk_return_date)
        self._validate_return(self.env['stock.picking'].browse(self._wizard(order, et).action_return_et()['res_id']))
        self.assertEqual(et.qty_returned_et, 1)
        self.assertFalse(et.bastk_return_date)

    def test_et_status_follows_the_units_of_a_partly_received_et_return(self):
        order = self._two_units()
        first, second = order.order_line
        self._delivery(order)
        receipt = self.env['stock.picking'].browse(self._wizard(order, first | second).action_return_et()['res_id'])
        self.assertEqual(order.et_status, 'requested')
        kept = receipt.move_ids.filtered(lambda move: move.sale_line_id == first)
        kept.write({'quantity': kept.product_uom_qty, 'picked': True})
        (receipt.move_ids - kept).write({'quantity': 0, 'picked': False})
        receipt.with_context(skip_backorder=True).button_validate()
        self.assertEqual(order.et_status, 'partially_returned')
        self.assertEqual(order.return_status, 'partial')
        self._validate_return(receipt.backorder_ids)
        self.assertEqual(second.qty_returned_et, 1)
        self.assertEqual(order.et_status, 'fully_returned')
        self.assertEqual(order.return_status, 'fully_returned')

    def test_cancelled_et_return_is_not_et(self):
        order = self._two_units()
        self._delivery(order)
        receipt = self.env['stock.picking'].browse(self._wizard(order, order.order_line[0]).action_return_et()['res_id'])
        self.assertEqual(order.et_status, 'requested')
        receipt.action_cancel()
        self.assertEqual(order.et_status, 'not_et')

    def test_et_status_is_for_rental_orders_only(self):
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        self.assertFalse(order.et_status)

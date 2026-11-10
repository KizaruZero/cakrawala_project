from datetime import date, datetime, timedelta
from unittest.mock import patch

from lxml import etree

from odoo import Command, fields
from odoo.exceptions import RedirectWarning, UserError
from odoo.tests import Form, tagged

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestActualDeliveryFromBastk(RentalBillingEngineInvoiceCommon):
    """Rental units take Actual Delivery from BASTK Submit Out, not from the DO."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={**cls.env.context, 'tz': 'Asia/Jakarta'})
        cls.product.write({'is_vehicle': True, 'is_storable': True, 'tracking': 'serial'})
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.customer_location = cls.env.ref('stock.stock_location_customers')
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'Actual Delivery Brand'})
        cls.model = cls.env['fleet.vehicle.model'].create({'name': 'Actual Delivery Model', 'brand_id': brand.id})
        cls.bastk_type = cls.env['bastk.type'].create({
            'name': 'Actual Delivery Rent', 'need_submit_out': True, 'need_submit_in': True, 'need_gi': True,
        })
        cls.tomorrow = fields.Date.context_today(cls.env.user) + timedelta(days=1)
        cls.year = cls.env['vehicle.year'].create({'name': '2099'})
        cls.color = cls.env['vehicle.color'].create({'name': 'Actual Delivery Color'})

    def _unit(self):
        lot = self.env['stock.lot'].create({'product_id': self.product.id, 'company_id': self.env.company.id})
        self.env['stock.quant']._update_available_quantity(self.product, self.warehouse.lot_stock_id, 1, lot_id=lot)
        return self.env['fleet.vehicle'].create({
            'model_id': self.model.id, 'lot_id': lot.id, 'company_id': self.env.company.id,
            'chassis_number': 'CH%s' % lot.id, 'engine_number': 'EN%s' % lot.id,
            'initial_license_plate': 'B %s ET' % lot.id,
            'model_year': self.year.name, 'color': self.color.name,
        })

    def _delivery(self, line, vehicle, validate=True):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.out_type_id.id,
            'partner_id': self.partner.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
            'move_ids': [Command.create({
                'product_id': line.product_id.id, 'product_uom_qty': 1,
                'product_uom': line.product_uom_id.id, 'sale_line_id': line.id,
                'location_id': self.warehouse.lot_stock_id.id,
                'location_dest_id': self.customer_location.id,
            })],
        })
        picking.action_confirm()
        picking.move_ids.write({'move_line_ids': [Command.clear()]})
        self.env['stock.move.line'].create({
            'move_id': picking.move_ids.id, 'picking_id': picking.id,
            'product_id': line.product_id.id, 'lot_id': vehicle.lot_id.id, 'quantity': 1,
            'location_id': self.warehouse.lot_stock_id.id, 'location_dest_id': self.customer_location.id,
        })
        picking.move_ids.picked = True
        if validate:
            picking.with_context(skip_backorder=True).button_validate()
        return picking

    def _bastk(self, picking, vehicle):
        return self.env['bastk.management'].create({
            'bastk_type_id': self.bastk_type.id, 'partner_id': self.partner.id,
            'vehicle_id': vehicle.id, 'picking_ids': [Command.link(picking.id)],
            'pic_keluar': 'PIC', 'call_number_keluar': '0812', 'odometer_out': 0,
            'customer_name_keluar': 'Customer', 'cakrawala_name_keluar': 'Cakrawala',
            'customer_sign_keluar': b'aWQ=', 'cakrawala_sign_keluar': b'aWQ=',
        })

    def _submit_out(self, bastk, day):
        selection = self.env['bastk.item.selection'].search([], limit=1)             or self.env['bastk.item.selection'].create({'name': 'Baik'})
        bastk.line_keluar_ids.filtered(lambda line: not line.display_type).write({'selection_id': selection.id})
        self.env['bastk.submit.wizard'].create({
            'bastk_id': bastk.id, 'submit_type': 'out', 'date': day,
            'pic': 'PIC', 'call_number': '0812', 'odometer': 0,
        }).action_confirm()
        self.assertEqual(bastk.state, 'submitted_outside')

    def _mark_masuk(self, bastk):
        selection = self.env['bastk.item.selection'].search([], limit=1)
        bastk.line_masuk_ids.filtered(lambda line: not line.display_type).write({'selection_id': selection.id})

    def _submit_in(self, bastk, day):
        self._mark_masuk(bastk)
        bastk.write({
            'customer_name_masuk': 'Customer', 'cakrawala_name_masuk': 'Cakrawala',
            'customer_sign_masuk': b'aWQ=', 'cakrawala_sign_masuk': b'aWQ=',
        })
        self.env['bastk.submit.wizard'].create({
            'bastk_id': bastk.id, 'submit_type': 'in', 'date': day,
            'pic': 'PIC', 'call_number': '0812', 'odometer': 0,
        }).action_confirm()
        self.assertEqual(bastk.state, 'submitted_inside')

    def _rental_line(self):
        return self._order(delivery=False).order_line

    def test_validating_the_delivery_no_longer_fills_rental_unit(self):
        line = self._rental_line()
        self._delivery(line, self._unit())
        self.assertFalse(line.actual_delivery_date)

    def test_submit_out_fills_tanggal_keluar_not_the_validate_date(self):
        line = self._rental_line()
        vehicle = self._unit()
        bastk = self._bastk(self._delivery(line, vehicle), vehicle)
        self.assertFalse(line.actual_delivery_date)
        self._submit_out(bastk, self.tomorrow)
        self.assertEqual(line.actual_delivery_date, self.tomorrow)

    def test_billing_engine_charges_the_unit_only_after_submit_out(self):
        start = datetime.combine(self.tomorrow.replace(day=1), datetime.min.time())
        order = self._order(start=start, months=2, delivery=False)
        line = order.order_line
        vehicle = self._unit()
        bastk = self._bastk(self._delivery(line, vehicle), vehicle)
        domain = [('sale_line_id', '=', line.id)]
        Engine = self.env['sale.order.billing.engine']
        self.assertFalse(sum(Engine.search(domain).mapped('amount')))
        self._submit_out(bastk, self.tomorrow)
        self.assertTrue(sum(Engine.search(domain).mapped('amount')))

    def test_stock_warning_is_not_raised_once_the_delivery_took_the_unit_out(self):
        line = self._rental_line()
        vehicle = self._unit()
        bastk = self._bastk(self._delivery(line, vehicle), vehicle)
        self.assertTrue(bastk.is_goods_issue_done)
        self.assertFalse(bastk._onchange_vehicle_stock_warning())

    def test_each_unit_follows_its_own_bastk(self):
        order = self._order(delivery=False, order_line=[
            Command.create(self._line_values(False)), Command.create(self._line_values(False)),
        ])
        first_line, second_line = order.order_line
        first, second = self._unit(), self._unit()
        first_bastk = self._bastk(self._delivery(first_line, first), first)
        self._bastk(self._delivery(second_line, second), second)
        self._submit_out(first_bastk, self.tomorrow)
        self.assertEqual(first_line.actual_delivery_date, self.tomorrow)
        self.assertFalse(second_line.actual_delivery_date)

    def test_date_filled_before_this_rule_is_replaced_by_submit_out(self):
        line = self._rental_line()
        vehicle = self._unit()
        bastk = self._bastk(self._delivery(line, vehicle), vehicle)
        line.actual_delivery_date = date(2026, 1, 1)
        self._submit_out(bastk, self.tomorrow)
        self.assertEqual(line.actual_delivery_date, self.tomorrow)

    def test_same_unit_delivered_again_keeps_the_date_its_rental_started(self):
        line = self._rental_line()
        vehicle = self._unit()
        first = self._bastk(self._delivery(line, vehicle), vehicle)
        self._submit_out(first, self.tomorrow)
        self._mark_masuk(first)
        first.state = 'done'
        lot = vehicle.lot_id
        self.env['stock.quant']._update_available_quantity(self.product, self.customer_location, -1, lot_id=lot)
        self.env['stock.quant']._update_available_quantity(self.product, self.warehouse.lot_stock_id, 1, lot_id=lot)
        again = self._bastk(self._delivery(line, vehicle), vehicle)
        self._submit_out(again, self.tomorrow + timedelta(days=5))
        self.assertEqual(line.actual_delivery_date, self.tomorrow)

    def test_line_changing_unit_takes_the_date_of_the_new_unit(self):
        line = self._rental_line()
        first, second = self._unit(), self._unit()
        self._submit_out(self._bastk(self._delivery(line, first), first), self.tomorrow)
        later = self.tomorrow + timedelta(days=5)
        self._submit_out(self._bastk(self._delivery(line, second), second), later)
        self.assertEqual(line.actual_delivery_date, later)

    def _multi_unit_delivery(self):
        order = self._order(delivery=False, order_line=[
            Command.create(self._line_values(False)), Command.create(self._line_values(False)),
        ])
        lines = order.order_line
        units = [self._unit(), self._unit()]
        location, customer = self.warehouse.lot_stock_id, self.customer_location
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.out_type_id.id, 'partner_id': self.partner.id,
            'location_id': location.id, 'location_dest_id': customer.id,
            'move_ids': [Command.create({
                'product_id': line.product_id.id, 'product_uom_qty': 1,
                'product_uom': line.product_uom_id.id, 'sale_line_id': line.id,
                'location_id': location.id, 'location_dest_id': customer.id,
            }) for line in lines],
        })
        picking.action_confirm()
        picking.move_line_ids.unlink()
        moves = {move.sale_line_id: move for move in picking.move_ids}
        for line, vehicle in zip(lines, units):
            self.env['stock.move.line'].create({
                'move_id': moves[line].id, 'picking_id': picking.id, 'product_id': line.product_id.id,
                'lot_id': vehicle.lot_id.id, 'quantity': 1,
                'location_id': location.id, 'location_dest_id': customer.id,
            })
        picking.move_ids.picked = True
        picking.with_context(skip_backorder=True).button_validate()
        self.assertEqual(picking.state, 'done')
        return picking, lines, units, moves

    def _bastks_of(self, picking, bastk_type=None):
        action = picking.action_create_bastk()
        self.assertEqual(action['res_model'], 'bastk.create.from.picking.wizard')
        self.env[action['res_model']].with_context(action['context']).create({
            'bastk_type_id': (bastk_type or self.bastk_type).id,
        }).action_confirm()
        for bastk in picking.source_bastk_ids:
            bastk.write({
                'pic_keluar': 'PIC', 'call_number_keluar': '0812', 'odometer_out': 0,
                'customer_name_keluar': 'Customer', 'cakrawala_name_keluar': 'Cakrawala',
                'customer_sign_keluar': b'aWQ=', 'cakrawala_sign_keluar': b'aWQ=',
            })
        return picking.source_bastk_ids

    def test_multi_unit_delivery_gets_one_bastk_per_unit(self):
        picking, _lines, units, _moves = self._multi_unit_delivery()
        self.assertEqual(picking.bastk_pending_vehicle_ids, units[0] | units[1])
        bastks = self._bastks_of(picking)
        self.assertEqual(bastks.vehicle_id, units[0] | units[1])
        self.assertFalse(picking.bastk_id)
        self.assertFalse(picking.bastk_pending_vehicle_ids)
        self.assertEqual(bastks.mapped('picking_count'), [1, 1])

    def test_each_line_of_a_multi_unit_delivery_follows_its_own_bastk(self):
        picking, lines, units, moves = self._multi_unit_delivery()
        bastks = self._bastks_of(picking)
        by_vehicle = {bastk.vehicle_id: bastk for bastk in bastks}
        later = self.tomorrow + timedelta(days=5)

        self._submit_out(by_vehicle[units[1]], later)
        self.assertFalse(lines[0].actual_delivery_date)
        self.assertEqual(lines[1].actual_delivery_date, later)

        self._submit_out(by_vehicle[units[0]], self.tomorrow)
        self.assertEqual(lines[0].actual_delivery_date, self.tomorrow)
        self.assertEqual(lines[1].actual_delivery_date, later)

        self.assertEqual(moves[lines[0]].bastk_unit_id, by_vehicle[units[0]])
        self.assertEqual(moves[lines[0]].bastk_out_date, self.tomorrow)
        self.assertEqual(moves[lines[1]].bastk_unit_id, by_vehicle[units[1]])
        self.assertEqual(moves[lines[1]].bastk_out_date, later)

    def test_single_unit_delivery_keeps_its_bastk_linked_directly(self):
        line = self._rental_line()
        vehicle = self._unit()
        picking = self._delivery(line, vehicle)
        self.assertFalse(picking.bastk_pending_vehicle_ids)
        self.assertEqual(picking.action_create_bastk()['res_model'], 'bastk.management')

    def test_submit_in_of_a_unit_receives_it_from_where_the_delivery_sent_it(self):
        with_gr = self.env['bastk.type'].create({
            'name': 'Actual Delivery Rent GR', 'need_submit_out': True, 'need_submit_in': True,
            'need_gi': True, 'need_gr': True,
        })
        picking, _lines, _units, _moves = self._multi_unit_delivery()
        bastk = self._bastks_of(picking, with_gr)[0]
        self._submit_out(bastk, self.tomorrow)
        self._mark_masuk(bastk)
        bastk.write({
            'pic_masuk': 'PIC', 'call_number_masuk': '0812', 'odometer_in': 0, 'end_date': self.tomorrow,
            'customer_name_masuk': 'Customer', 'cakrawala_name_masuk': 'Cakrawala',
            'customer_sign_masuk': b'aWQ=', 'cakrawala_sign_masuk': b'aWQ=',
        })
        bastk.with_context(skip_submit_wizard=True).action_submit_inside()
        receipt = bastk.picking_ids.filtered(lambda p: p.picking_type_code == 'incoming')
        self.assertEqual(receipt.location_id, self.customer_location)
        self.assertEqual(receipt.state, 'done')

    def _return(self, picking, moves):
        wizard = self.env['stock.return.picking'].with_context(
            active_id=picking.id, active_model='stock.picking').create({'picking_id': picking.id})
        wizard.product_return_moves.filtered(lambda line: line.move_id in moves).quantity = 1
        wizard.product_return_moves.filtered(lambda line: line.move_id not in moves).quantity = 0
        return wizard._create_return()

    def test_return_of_one_unit_continues_its_own_bastk(self):
        picking, lines, units, moves = self._multi_unit_delivery()
        bastks = self._bastks_of(picking)
        by_vehicle = {bastk.vehicle_id: bastk for bastk in bastks}
        returned = self._return(picking, moves[lines[0]])
        self.assertEqual(returned.bastk_id, by_vehicle[units[0]])

    def test_return_of_units_with_their_own_bastk_is_refused_together(self):
        picking, _lines, _units, _moves = self._multi_unit_delivery()
        bastks = self._bastks_of(picking)
        with self.assertRaisesRegex(RedirectWarning, 'BASTK masing-masing') as caught:
            self._return(picking, picking.move_ids)
        action = caught.exception.args[1]
        self.assertEqual(action['res_model'], 'bastk.management')
        self.assertEqual(set(action['domain'][0][2]), set(bastks.ids))

    def _with_gr(self):
        return self.env['bastk.type'].create({
            'name': 'Actual Delivery Rent GR', 'need_submit_out': True, 'need_submit_in': True,
            'need_gi': True, 'need_gr': True,
        })

    def _out_with_gr(self):
        """Two units of one delivery, each out on its own BASTK of a type receiving them on Submit In."""
        picking, lines, units, moves = self._multi_unit_delivery()
        by_vehicle = {bastk.vehicle_id: bastk for bastk in self._bastks_of(picking, self._with_gr())}
        for bastk in by_vehicle.values():
            self._submit_out(bastk, self.tomorrow)
        return picking, lines, units, moves, by_vehicle

    def _receive(self, receipt):
        receipt.move_ids.picked = True
        receipt.with_context(skip_backorder=True).button_validate()
        self.assertEqual(receipt.state, 'done')

    def _assert_returned(self, bastk, line, delivery_move):
        receipt = bastk.picking_ids.filtered(lambda p: p.picking_type_code == 'incoming')
        self.assertEqual(len(receipt), 1)
        self.assertEqual(receipt.state, 'done')
        self.assertEqual(line.qty_returned, 1)
        self.assertEqual(line.bastk_return_date, self.tomorrow)
        self.assertEqual(receipt.sale_id, line.order_id)
        self.assertEqual(receipt.return_id, delivery_move.picking_id)
        self.assertEqual(receipt.move_ids.sale_line_id, line)
        self.assertEqual(receipt.move_ids.origin_returned_move_id, delivery_move)
        self.assertTrue(receipt.move_ids.to_refund)

    def test_submit_in_behaves_like_the_return_from_the_order(self):
        picking, lines, units, moves, by_vehicle = self._out_with_gr()
        order = lines.order_id
        Engine = self.env['sale.order.billing.engine']
        amounts = Engine.search([('sale_line_id', 'in', lines.ids)]).mapped(lambda row: (row.period_start, row.amount))

        self._submit_in(by_vehicle[units[0]], self.tomorrow)
        self._assert_returned(by_vehicle[units[0]], lines[0], moves[lines[0]])
        self.assertEqual(lines[1].qty_returned, 0)
        self.assertEqual(order.return_status, 'partial')
        self.assertTrue(order.show_return_button)

        receipt = self._return(picking, moves[lines[1]])
        self.assertEqual(receipt.bastk_id, by_vehicle[units[1]])
        self._receive(receipt)
        self._submit_in(by_vehicle[units[1]], self.tomorrow)
        self._assert_returned(by_vehicle[units[1]], lines[1], moves[lines[1]])
        self.assertEqual(order.return_status, 'fully_returned')
        self.assertFalse(order.show_return_button)
        self.assertEqual(
            Engine.search([('sale_line_id', 'in', lines.ids)]).mapped(lambda row: (row.period_start, row.amount)),
            amounts,
        )

    def test_submit_in_after_the_et_return_keeps_both_statuses(self):
        _picking, lines, units, _moves, by_vehicle = self._out_with_gr()
        order = lines.order_id
        action = order.action_request_early_termination()
        model = self.env[action['res_model']].with_context(**action['context'])
        with Form(model, view='x_sale_purchase_custom.view_rental_return_picking_et_form') as form:
            for index in range(len(form.line_ids)):
                with form.line_ids.edit(index) as row:
                    if row.sale_line_id == lines[0]:
                        row.quantity = 1
        receipt = self.env['stock.picking'].browse(form.save().action_return_et()['res_id'])
        self.assertEqual(order.et_status, 'requested')
        self._receive(receipt)
        self.assertFalse(lines[0].bastk_return_date)
        self._submit_in(by_vehicle[units[0]], self.tomorrow)
        self.assertEqual(lines[0].bastk_return_date, self.tomorrow)
        self.assertEqual((lines[0].qty_returned, lines[0].qty_returned_et), (0, 1))
        self.assertEqual(order.return_status, 'partial')
        self.assertEqual(order.et_status, 'fully_returned')

    def test_create_goods_receive_button_links_the_delivery_too(self):
        picking, lines, units, moves, by_vehicle = self._out_with_gr()
        bastk = by_vehicle[units[0]]
        action = self.env['bastk.picking.wizard'].create({
            'bastk_id': bastk.id, 'picking_type_code': 'incoming',
            'picking_type_id': self.warehouse.in_type_id.id,
        }).action_create_picking()
        receipt = self.env['stock.picking'].browse(action['res_id'])
        self.assertEqual(receipt.sale_id, lines.order_id)
        self.assertEqual(receipt.return_id, picking)
        self.assertEqual(receipt.move_ids.sale_line_id, lines[0])
        self.assertEqual(receipt.move_ids.origin_returned_move_id, moves[lines[0]])

    def test_goods_receive_without_a_delivery_of_the_unit_is_not_linked(self):
        vehicle = self._unit()
        bastk = self.env['bastk.management'].create({
            'bastk_type_id': self._with_gr().id, 'partner_id': self.partner.id, 'vehicle_id': vehicle.id,
        })
        self.assertEqual(bastk._get_return_link_vals(), ({}, {}))

    def test_unit_back_through_submit_in_leaves_the_return_popup(self):
        picking, lines, units, moves, by_vehicle = self._out_with_gr()
        self._submit_in(by_vehicle[units[0]], self.tomorrow)
        wizard = self.env['stock.return.picking'].with_context(
            active_id=picking.id, active_model='stock.picking').create({'picking_id': picking.id})
        self.assertEqual(wizard.product_return_moves.move_id, moves[lines[1]])
        action = wizard.action_create_returns_all()
        receipt = self.env['stock.picking'].browse(action['res_id'])
        self.assertEqual(receipt.bastk_id, by_vehicle[units[1]])
        self.assertEqual(receipt.move_ids.sale_line_id, lines[1])

    def test_popup_opened_before_the_unit_came_back_is_refused(self):
        picking, lines, units, moves, by_vehicle = self._out_with_gr()
        wizard = self.env['stock.return.picking'].with_context(
            active_id=picking.id, active_model='stock.picking').create({'picking_id': picking.id})
        self._submit_in(by_vehicle[units[0]], self.tomorrow)
        wizard.product_return_moves.filtered(lambda line: line.move_id == moves[lines[0]]).quantity = 1
        with self.assertRaisesRegex(UserError, 'sudah kembali'):
            wizard._create_return()

    def test_delivery_with_every_unit_back_has_nothing_to_return(self):
        picking, _lines, units, _moves, by_vehicle = self._out_with_gr()
        for vehicle in units:
            self._submit_in(by_vehicle[vehicle], self.tomorrow)
        with self.assertRaisesRegex(UserError, 'sudah kembali'):
            self.env['stock.return.picking'].with_context(
                active_id=picking.id, active_model='stock.picking').create({'picking_id': picking.id})

    def test_return_from_the_order_skips_the_delivery_whose_unit_is_back(self):
        order = self._order(delivery=False, order_line=[
            Command.create(self._line_values(False)), Command.create(self._line_values(False)),
        ])
        first_line, second_line = order.order_line
        first, second = self._unit(), self._unit()
        first_delivery = self._delivery(first_line, first)
        bastk = self._bastk(self._delivery(second_line, second), second)
        bastk.bastk_type_id = self._with_gr()
        self._submit_out(bastk, self.tomorrow)
        self._submit_in(bastk, self.tomorrow)
        self.assertEqual(second_line.qty_returned, 1)
        self.assertEqual(order.action_return_from_ro()['context']['default_picking_id'], first_delivery.id)

    def test_sales_order_of_the_bastk_shows_whenever_it_is_known(self):
        arch = etree.fromstring(self.env['stock.picking'].get_view(view_type='form')['arch'])
        field = arch.xpath("//field[@name='bastk_sale_order_id']")[0]
        self.assertEqual(field.get('invisible'), 'not bastk_sale_order_id')

    def test_vehicle_other_than_the_delivered_unit_is_reported(self):
        line = self._rental_line()
        delivered, other = self._unit(), self._unit()
        bastk = self._bastk(self._delivery(line, delivered), other)
        self._submit_out(bastk, self.tomorrow)
        self.assertFalse(line.actual_delivery_date)
        self.assertIn('Actual Delivery', ''.join(bastk.message_ids.mapped('body')))

    def test_bastk_with_its_own_goods_issue_touches_no_order(self):
        line = self._rental_line()
        vehicle = self._unit()
        bastk = self.env['bastk.management'].create({
            'bastk_type_id': self.bastk_type.id, 'partner_id': self.partner.id, 'vehicle_id': vehicle.id,
            'pic_keluar': 'PIC', 'call_number_keluar': '0812', 'odometer_out': 0,
            'customer_name_keluar': 'Customer', 'cakrawala_name_keluar': 'Cakrawala',
            'customer_sign_keluar': b'aWQ=', 'cakrawala_sign_keluar': b'aWQ=',
        })
        self._submit_out(bastk, self.tomorrow)
        self.assertFalse(line.actual_delivery_date)

    def test_non_fleet_rental_line_still_uses_validate_date_in_local_time(self):
        self.product.write({'is_vehicle': False, 'tracking': 'none'})
        line = self._rental_line()
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.out_type_id.id, 'partner_id': self.partner.id,
            'location_id': self.warehouse.lot_stock_id.id, 'location_dest_id': self.customer_location.id,
            'move_ids': [Command.create({
                'product_id': line.product_id.id, 'product_uom_qty': 1,
                'product_uom': line.product_uom_id.id, 'sale_line_id': line.id,
                'location_id': self.warehouse.lot_stock_id.id, 'location_dest_id': self.customer_location.id,
            })],
        })
        picking.action_confirm()
        picking.move_ids.write({'quantity': 1, 'picked': True})
        # 18:30 UTC on the 10th is already 01:30 on the 11th in Jakarta.
        with patch.object(fields.Datetime, 'now', return_value=datetime(2026, 3, 10, 18, 30)):
            picking.with_context(skip_backorder=True).button_validate()
        self.assertEqual(line.actual_delivery_date, date(2026, 3, 11))

    def test_submit_in_fills_return_date_with_tanggal_masuk(self):
        line = self._rental_line()
        vehicle = self._unit()
        bastk = self._bastk(self._delivery(line, vehicle), vehicle)
        planned = self.tomorrow + timedelta(days=30)
        bastk.end_date = planned
        self._submit_out(bastk, self.tomorrow)
        self.assertFalse(line.bastk_return_date)
        back = self.tomorrow + timedelta(days=3)
        self._submit_in(bastk, back)
        self.assertEqual(line.bastk_return_date, back)

    def test_each_line_of_a_multi_unit_delivery_has_its_own_return_date(self):
        picking, lines, units, _moves = self._multi_unit_delivery()
        by_vehicle = {bastk.vehicle_id: bastk for bastk in self._bastks_of(picking)}
        for bastk in by_vehicle.values():
            self._submit_out(bastk, self.tomorrow)
        back = self.tomorrow + timedelta(days=3)
        self._submit_in(by_vehicle[units[1]], back)
        self.assertFalse(lines[0].bastk_return_date)
        self.assertEqual(lines[1].bastk_return_date, back)
        later = self.tomorrow + timedelta(days=7)
        self._submit_in(by_vehicle[units[0]], later)
        self.assertEqual(lines[0].bastk_return_date, later)
        self.assertEqual(lines[1].bastk_return_date, back)

    def test_delivering_the_unit_again_empties_the_return_date(self):
        line = self._rental_line()
        vehicle = self._unit()
        first = self._bastk(self._delivery(line, vehicle), vehicle)
        self._submit_out(first, self.tomorrow)
        self._submit_in(first, self.tomorrow)
        self.assertEqual(line.bastk_return_date, self.tomorrow)
        first.state = 'done'
        lot = vehicle.lot_id
        self.env['stock.quant']._update_available_quantity(self.product, self.customer_location, -1, lot_id=lot)
        self.env['stock.quant']._update_available_quantity(self.product, self.warehouse.lot_stock_id, 1, lot_id=lot)
        again = self._bastk(self._delivery(line, vehicle), vehicle)
        self._submit_out(again, self.tomorrow + timedelta(days=5))
        self.assertFalse(line.bastk_return_date)

    def test_return_date_is_information_only(self):
        start = datetime.combine(self.tomorrow.replace(day=1), datetime.min.time())
        order = self._order(start=start, months=2, delivery=False)
        line = order.order_line
        vehicle = self._unit()
        bastk = self._bastk(self._delivery(line, vehicle), vehicle)
        self._submit_out(bastk, self.tomorrow)
        Engine = self.env['sale.order.billing.engine']
        billing = Engine.search([('sale_line_id', '=', line.id)]).mapped(lambda row: (row.period_start, row.amount))
        returned, status = (line.qty_returned, line.qty_returned_et), order.rental_status
        self._submit_in(bastk, self.tomorrow)
        self.assertEqual(
            Engine.search([('sale_line_id', '=', line.id)]).mapped(lambda row: (row.period_start, row.amount)), billing)
        self.assertEqual((line.qty_returned, line.qty_returned_et), returned)
        self.assertEqual(order.rental_status, status)

    def test_bastk_without_a_rental_delivery_touches_no_return_date(self):
        line = self._rental_line()
        vehicle = self._unit()
        bastk = self.env['bastk.management'].create({
            'bastk_type_id': self.bastk_type.id, 'partner_id': self.partner.id, 'vehicle_id': vehicle.id,
            'pic_keluar': 'PIC', 'call_number_keluar': '0812', 'odometer_out': 0,
            'customer_name_keluar': 'Customer', 'cakrawala_name_keluar': 'Cakrawala',
            'customer_sign_keluar': b'aWQ=', 'cakrawala_sign_keluar': b'aWQ=',
        })
        self._submit_out(bastk, self.tomorrow)
        self._submit_in(bastk, self.tomorrow)
        self.assertFalse(line.bastk_return_date)

    def test_return_date_column_is_right_of_returned_et(self):
        arch = self.env['sale.order'].get_view(self.env.ref('sale.view_order_form').id)['arch']
        columns = etree.fromstring(arch).xpath("//field[@name='order_line']//list/field/@name")
        self.assertEqual(columns[columns.index('qty_returned_et') + 1], 'bastk_return_date')

    def test_duplicated_order_does_not_copy_return_date(self):
        order = self._order()
        order.order_line.write({'bastk_return_date': self.tomorrow})
        self.assertFalse(order.copy().order_line.bastk_return_date)

    def test_duplicated_order_does_not_copy_actual_delivery(self):
        order = self._order()
        self.assertTrue(order.order_line.actual_delivery_date)
        self.assertFalse(order.copy().order_line.actual_delivery_date)

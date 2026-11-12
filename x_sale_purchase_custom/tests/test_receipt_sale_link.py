from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestReceiptSaleLink(RentalBillingEngineInvoiceCommon):
    """A unit received for a Rental Order is paired with one of its lines, delivery or not."""

    def setUp(self):
        super().setUp()
        self.warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1)
        self.unit_product = self.env['product.product'].create({
            'name': 'GR Unit Without Delivery', 'is_storable': True, 'tracking': 'serial',
            'rent_ok': True, 'is_vehicle': True,
        })
        self.order = self._order(state='draft', order_line=[
            Command.create(self._line_values(product_id=self.unit_product.id, analytic_distribution=False))])

    def _receive(self, order):
        """The unit is in stock and its receipt pairs it with ``order``."""
        product = order.order_line.product_id
        stock = self.warehouse.lot_stock_id
        lot = self.env['stock.lot'].create({
            'name': 'GR-NO-DELIVERY-1', 'product_id': product.id, 'analytic_account_id': self.unit_account.id,
        })
        self.env['stock.quant']._update_available_quantity(product, stock, 1, lot_id=lot)
        supplier = self.env.ref('stock.stock_location_suppliers')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'location_id': supplier.id,
            'location_dest_id': stock.id,
            'move_ids': [Command.create({
                'product_id': product.id, 'product_uom_qty': 1,
                'location_id': supplier.id, 'location_dest_id': stock.id,
            })],
        })
        picking.action_confirm()
        picking.move_ids.move_line_ids.unlink()
        self.env['stock.move.line'].create({
            'move_id': picking.move_ids.id, 'picking_id': picking.id, 'product_id': product.id,
            'lot_id': lot.id, 'quantity': 1, 'location_id': supplier.id, 'location_dest_id': stock.id,
        })
        with patch.object(type(self.env.user), '_bus_send', autospec=True) as bus_send:
            picking._link_received_units_to_sale_order(order)
        self.receipt, self.bus_send = picking, bus_send
        return lot

    def assertToldNotOnDelivery(self, next_step):
        note = self.receipt.message_ids[:1].body
        self.assertIn('GR-NO-DELIVERY-1', note)
        self.assertIn('belum punya Delivery Order yang terbuka', note)
        self.assertIn(next_step, note)
        self.bus_send.assert_called_once()
        kind, payload = self.bus_send.call_args.args[1:]
        self.assertEqual(kind, 'simple_notification')
        self.assertEqual(payload['type'], 'warning')
        self.assertIn(self.order.name, payload['message'])

    def test_unit_received_for_an_order_line_without_open_delivery_is_paired(self):
        self.assertFalse(self.order.order_line.move_ids)
        self._receive(self.order)
        self.assertEqual(self.order.order_line.analytic_distribution, {str(self.unit_account.id): 100})
        self.assertToldNotOnDelivery('di-Confirm')

    def test_confirmed_order_without_open_delivery_asks_to_pick_the_unit_manually(self):
        self.order.state = 'sale'
        self._receive(self.order)
        self.assertToldNotOnDelivery('secara manual')

    def test_unit_paired_before_confirmation_is_on_the_delivery_once_the_order_is_confirmed(self):
        lot = self._receive(self.order)
        self.order.customer_po_amount = self.order.amount_total
        self.order.action_confirm()
        delivery = self.order.order_line.move_ids.filtered(lambda move: move.picking_code == 'outgoing')
        self.assertTrue(delivery)
        self.assertEqual(delivery.move_line_ids.lot_id, lot)

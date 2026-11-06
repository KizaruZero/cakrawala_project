import re

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .test_disposal_aging import DisposalFlowCommon


@tagged("post_install", "-at_install")
class TestDisposalDeliveryPayment(DisposalFlowCommon):
    """A disposal delivery is validated only once every invoice of its order is Paid."""

    def setUp(self):
        super().setUp()
        self._move_to(self.disposal)
        self.order = self._create_order()

    def _assert_refused(self, message):
        picking = self.order.picking_ids
        picking.action_assign()
        picking.move_ids.write({"quantity": 1, "picked": True})
        with self.assertRaisesRegex(ValidationError, message):
            picking.button_validate()
        self.assertNotEqual(picking.state, "done")
        self.assertEqual(self.vehicle.fleet_sub_status_id, self.disposal)
        self.assertFalse(self.lot.quant_ids.filtered(lambda quant: quant.location_id.usage == "customer"))

    def test_no_invoice_is_refused(self):
        self._assert_refused("Belum ada invoice")

    def test_draft_unpaid_and_in_payment_invoices_are_refused(self):
        invoice = self.order._create_invoices()
        self._assert_refused(re.escape(invoice.display_name))
        invoice.action_post()
        self._assert_refused("Not Paid")
        self._pay(invoice, fields.Date.today(), reconciled=False)
        self._assert_refused("In Payment")

    def test_quantities_still_to_invoice_are_refused(self):
        self._pay(self._invoice(self.order), fields.Date.today())
        service = self.env["product.product"].create({"name": "Fee", "type": "service", "invoice_policy": "order"})
        self.env["sale.order.line"].create({"order_id": self.order.id, "product_id": service.id, "price_unit": 100})
        self._assert_refused("belum ditagih")

    def test_paid_order_is_delivered_and_sold(self):
        self._pay(self._invoice(self.order), fields.Date.today())
        self._deliver(self.order)

    def test_paid_order_is_delivered_by_a_user_without_invoice_access(self):
        self._pay(self._invoice(self.order), fields.Date.today())
        user = self.env["res.users"].create({
            "name": "Disposal Warehouse", "login": "disposal_warehouse",
            "group_ids": [(6, 0, [self.env.ref("stock.group_stock_user").id])],
        })
        picking = self.order.picking_ids
        picking.action_assign()
        picking.move_ids.write({"quantity": 1, "picked": True})
        picking.with_user(user)._check_disposal_paid_before_validate()

    def test_delivery_of_a_regular_order_is_not_checked(self):
        product = self.env["product.product"].create({"name": "Regular Goods", "is_storable": True, "invoice_policy": "order"})
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        self.env["stock.quant"]._update_available_quantity(product, warehouse.lot_stock_id, 1)
        order = self.env["sale.order"].create({
            "partner_id": self.buyer.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": 1, "price_unit": 10})],
        })
        order.action_confirm()
        picking = order.picking_ids
        picking.action_assign()
        picking.move_ids.write({"quantity": 1, "picked": True})
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        self.assertFalse(order.invoice_ids)

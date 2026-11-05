from freezegun import freeze_time

from odoo import fields
from odoo.tests import TransactionCase, tagged


class DisposalFlowCommon(TransactionCase):
    """The real disposal flow: bidding, delivery, invoice and payment."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sold = cls.env.ref("x_stock_asset_receipt.vehicle_substatus_sold")
        cls.disposal = cls.env.ref("x_stock_asset_receipt.vehicle_substatus_disposal")
        cls.short_term = cls.env.ref("x_stock_asset_receipt.vehicle_substatus_short_term")
        cls.buyer = cls.env["res.partner"].create({"name": "Aging Buyer"})
        cls.product = cls.env["product.product"].create({
            "name": "Aging Unit",
            "is_storable": True,
            "tracking": "serial",
            "invoice_policy": "order",
            "is_vehicle": True,
        })
        cls.lot = cls.env["stock.lot"].create({
            "name": "AGING-001",
            "product_id": cls.product.id,
            "company_id": cls.env.company.id,
        })
        warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.env.company.id)], limit=1)
        cls.env["stock.quant"]._update_available_quantity(cls.product, warehouse.lot_stock_id, 1, lot_id=cls.lot)
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "Aging Brand"})
        model = cls.env["fleet.vehicle.model"].create({"name": "Aging Model", "brand_id": brand.id})
        cls.vehicle = cls.env["fleet.vehicle"].create({
            "model_id": model.id,
            "license_plate": "B 18 AGE",
            "lot_id": cls.lot.id,
            "fleet_sub_status_id": cls.short_term.id,
            "state_id": cls.short_term.state_id.id,
        })

    def _aging(self):
        self.vehicle.invalidate_recordset(["disposal_aging"])
        return self.vehicle.disposal_aging

    def _move_to(self, sub_status):
        self.vehicle._set_fleet_status(sub_status=sub_status)
        # Status changes are separate requests: nothing stays pending between them.
        self.env.flush_all()

    def _create_order(self):
        bidding = self.env["disposal.bidding"].create({
            "vehicle_id": self.vehicle.id,
            "bidding_line_ids": [(0, 0, {"partner_id": self.buyer.id, "bidding_price": 1000})],
        })
        order = bidding._create_sale_order()
        order.action_confirm()
        return order

    def _deliver(self, order):
        picking = order.picking_ids
        picking.action_assign()
        picking.move_ids.write({"quantity": 1, "picked": True})
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        self.assertEqual(self.vehicle.fleet_sub_status_id, self.sold)
        self.assertTrue(self.vehicle.is_fleet_locked)

    def _invoice(self, order):
        invoice = order._create_invoices()
        invoice.action_post()
        return invoice

    def _pay(self, invoice, date, reconciled=True):
        """A journal posting on the bank account itself is Paid at once; otherwise it waits In Payment."""
        journal = self.env["account.journal"].search([
            ("type", "=", "bank"), ("company_id", "=", invoice.company_id.id),
        ], limit=1)
        method = journal.inbound_payment_method_line_ids[:1]
        method.payment_account_id = journal.default_account_id if reconciled else False
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({
            "payment_date": date, "journal_id": journal.id, "payment_method_line_id": method.id,
        }).action_create_payments()
        self.assertEqual(invoice.payment_state, "paid" if reconciled else "in_payment")
        return invoice.matched_payment_ids

    def _add_invoice_for_a_new_line(self, order):
        """A second invoice on the same order, left in draft."""
        service = self.env["product.product"].create({"name": "Admin Fee", "type": "service", "invoice_policy": "order"})
        self.env["sale.order.line"].create({"order_id": order.id, "product_id": service.id, "price_unit": 100})
        return order._create_invoices()


@tagged("post_install", "-at_install")
class TestDisposalAging(DisposalFlowCommon):
    """Aging Disposal on the vehicle."""

    def test_vehicle_never_in_disposal_has_no_aging(self):
        self.assertFalse(self.vehicle.disposal_start_date)
        self.assertEqual(self._aging(), 0)
        with freeze_time("2026-01-01 12:00:00"):
            self._move_to(self.sold)
        self.assertFalse(self.vehicle.disposal_start_date)
        self.assertFalse(self.vehicle.disposal_end_date)

    def test_aging_runs_until_sold_and_paid(self):
        with freeze_time("2026-01-01 12:00:00"):
            self._move_to(self.disposal)
            self.assertEqual(self.vehicle.disposal_start_date, fields.Date.to_date("2026-01-01"))
            self.assertEqual(self._aging(), 0)
        with freeze_time("2026-01-11 12:00:00"):
            self.assertEqual(self._aging(), 10)
            order = self._create_order()

        # Sold is not the end: the money is still outstanding, on a vehicle that is locked by now.
        with freeze_time("2026-02-01 12:00:00"):
            self._deliver(order)
            self.assertFalse(self.vehicle.disposal_end_date)
            self.assertEqual(self._aging(), 31)
            invoice = self._invoice(order)
            self.assertFalse(self.vehicle.disposal_end_date)

        with freeze_time("2026-03-05 12:00:00"):
            payment = self._pay(invoice, "2026-03-01")
            self.assertEqual(self.vehicle.disposal_end_date, fields.Date.to_date("2026-03-01"))
            self.assertEqual(self._aging(), 59)

        with freeze_time("2026-06-01 12:00:00"):
            self.assertEqual(self._aging(), 59)

            payment.action_draft()
            payment.action_cancel()
            self.assertFalse(self.vehicle.disposal_end_date)
            self.assertEqual(self._aging(), 151)

    def test_in_payment_does_not_end_the_aging(self):
        with freeze_time("2026-01-01 12:00:00"):
            self._move_to(self.disposal)
            order = self._create_order()
            self._deliver(order)
            self._pay(self._invoice(order), "2026-01-05", reconciled=False)
            self.assertFalse(self.vehicle.disposal_end_date)

    def test_every_invoice_of_the_order_must_be_paid(self):
        with freeze_time("2026-01-01 12:00:00"):
            self._move_to(self.disposal)
            order = self._create_order()
            self._deliver(order)
            self._pay(self._invoice(order), "2026-01-05")
            self.assertEqual(self.vehicle.disposal_end_date, fields.Date.to_date("2026-01-05"))

            second = self._add_invoice_for_a_new_line(order)
            self.assertEqual(second.state, "draft")
            self.assertFalse(self.vehicle.disposal_end_date)
            second.action_post()
            self.assertFalse(self.vehicle.disposal_end_date)
            self._pay(second, "2026-01-09")
            self.assertEqual(self.vehicle.disposal_end_date, fields.Date.to_date("2026-01-09"))

    def test_payment_before_delivery_ends_on_delivery(self):
        with freeze_time("2026-01-01 12:00:00"):
            self._move_to(self.disposal)
            order = self._create_order()
            self._pay(self._invoice(order), "2026-01-05")
            self.assertFalse(self.vehicle.disposal_end_date)
        with freeze_time("2026-01-21 12:00:00"):
            self._deliver(order)
            self.assertEqual(self.vehicle.disposal_end_date, fields.Date.to_date("2026-01-21"))
            self.assertEqual(self._aging(), 20)

    def test_sold_without_a_disposal_delivery_ends_on_that_day(self):
        with freeze_time("2026-01-01 12:00:00"):
            self._move_to(self.disposal)
        with freeze_time("2026-01-16 12:00:00"):
            self._move_to(self.sold)
            self.assertEqual(self.vehicle.disposal_end_date, fields.Date.to_date("2026-01-16"))
        with freeze_time("2026-02-01 12:00:00"):
            self.assertEqual(self._aging(), 15)

    def test_leaving_disposal_resets_and_coming_back_restarts(self):
        with freeze_time("2026-01-01 12:00:00"):
            self._move_to(self.disposal)
        with freeze_time("2026-01-10 12:00:00"):
            self._move_to(self.short_term)
            self.assertFalse(self.vehicle.disposal_start_date)
            self.assertEqual(self._aging(), 0)
        with freeze_time("2026-02-01 12:00:00"):
            self._move_to(self.disposal)
            self.assertEqual(self.vehicle.disposal_start_date, fields.Date.to_date("2026-02-01"))

    def test_status_correction_from_sold_reopens_the_aging(self):
        with freeze_time("2026-01-01 12:00:00"):
            self._move_to(self.disposal)
        with freeze_time("2026-01-16 12:00:00"):
            self._move_to(self.sold)
        with freeze_time("2026-02-01 12:00:00"):
            self.vehicle.with_context(import_file=True).write({
                "fleet_sub_status_id": self.disposal.id,
                "state_id": self.disposal.state_id.id,
            })
            self.assertEqual(self.vehicle.disposal_start_date, fields.Date.to_date("2026-01-01"))
            self.assertFalse(self.vehicle.disposal_end_date)
            self.assertEqual(self._aging(), 31)

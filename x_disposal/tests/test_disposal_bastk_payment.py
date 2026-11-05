import re

from lxml import etree

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .test_disposal_aging import DisposalFlowCommon


@tagged("post_install", "-at_install")
class TestDisposalBastkPayment(DisposalFlowCommon):
    """Submit Out of a disposal BASTK waits until every invoice of its order is Paid."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vehicle._set_fleet_status(sub_status=cls.disposal)
        cls.paid_type = cls._bastk_type("Disposal Paid", require_invoice_paid=True)
        cls.free_type = cls._bastk_type("Disposal Free")

    @classmethod
    def _bastk_type(cls, name, **vals):
        return cls.env["bastk.type"].create({
            "name": name, "is_disposal": True, "need_submit_out": True, "need_submit_in": False,
            "out_substate_id": cls.sold.id, "out_state_id": cls.sold.state_id.id, **vals,
        })

    def _bastk(self, bastk_type=None, order=None):
        order = order if order is not None else self.order
        bastk = self.env["bastk.management"].with_context(skip_submit_wizard=True).create({
            "bastk_type_id": (bastk_type or self.paid_type).id,
            "partner_id": self.buyer.id,
            "vehicle_id": self.vehicle.id,
            "sale_order_id": order.id,
        })
        lines = bastk.line_keluar_ids.filtered(lambda line: not line.display_type)
        if lines:
            lines.write({"condition_baik": True})
        else:
            self.env["bastk.description"].create({
                "bastk_id": bastk.id, "bastk_type": "keluar", "name": "Unit", "condition_baik": True,
            })
        bastk.write({
            "customer_sign_keluar": "eA==", "customer_name_keluar": "Buyer",
            "cakrawala_sign_keluar": "eA==", "cakrawala_name_keluar": "Cakrawala",
            "pic_keluar": "PIC", "call_number_keluar": "0812",
            "start_date": fields.Date.context_today(bastk), "odometer_out": 500,
        })
        return bastk

    def setUp(self):
        super().setUp()
        self.order = self._create_order()
        self._deliver(self.order)

    def test_no_invoice_is_refused(self):
        bastk = self._bastk()
        with self.assertRaisesRegex(ValidationError, "Belum ada invoice"):
            bastk.action_submit_outside()
        self.assertEqual(bastk.state, "draft")

    def test_refused_before_the_signature_wizard_opens(self):
        bastk = self._bastk().with_context(skip_submit_wizard=False)
        with self.assertRaisesRegex(ValidationError, "Belum ada invoice"):
            bastk.action_submit_outside()

    def test_draft_invoice_is_refused(self):
        invoice = self.order._create_invoices()
        self.assertEqual(invoice.state, "draft")
        with self.assertRaisesRegex(ValidationError, re.escape(invoice.display_name)):
            self._bastk().action_submit_outside()

    def test_posted_unpaid_invoice_is_refused(self):
        self._invoice(self.order)
        with self.assertRaisesRegex(ValidationError, "Not Paid"):
            self._bastk().action_submit_outside()

    def test_in_payment_is_refused(self):
        self._pay(self._invoice(self.order), fields.Date.today(), reconciled=False)
        with self.assertRaisesRegex(ValidationError, "In Payment"):
            self._bastk().action_submit_outside()

    def test_paid_invoice_passes(self):
        self._pay(self._invoice(self.order), fields.Date.today())
        bastk = self._bastk()
        bastk.action_submit_outside()
        self.assertEqual(bastk.state, "submitted_outside")

    def test_every_invoice_of_the_order_is_checked(self):
        self._pay(self._invoice(self.order), fields.Date.today())
        second = self._add_invoice_for_a_new_line(self.order)
        bastk = self._bastk()
        with self.assertRaisesRegex(ValidationError, re.escape(second.display_name)):
            bastk.action_submit_outside()
        second.action_post()
        with self.assertRaisesRegex(ValidationError, "Not Paid"):
            bastk.action_submit_outside()
        self._pay(second, fields.Date.today())
        bastk.action_submit_outside()
        self.assertEqual(bastk.state, "submitted_outside")

    def test_quantities_still_to_invoice_are_refused(self):
        self._pay(self._invoice(self.order), fields.Date.today())
        service = self.env["product.product"].create({"name": "Fee", "type": "service", "invoice_policy": "order"})
        self.env["sale.order.line"].create({"order_id": self.order.id, "product_id": service.id, "price_unit": 100})
        with self.assertRaisesRegex(ValidationError, "belum ditagih"):
            self._bastk().action_submit_outside()

    def test_cancelled_invoice_is_ignored(self):
        self.order._create_invoices().button_cancel()
        self._pay(self._invoice(self.order), fields.Date.today())
        bastk = self._bastk()
        bastk.action_submit_outside()
        self.assertEqual(bastk.state, "submitted_outside")

    def test_credited_invoice_leaves_the_order_to_invoice_again(self):
        invoice = self._invoice(self.order)
        self.env["account.move.reversal"].with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({"journal_id": invoice.journal_id.id, "date": fields.Date.today()}).modify_moves()
        self.assertEqual(invoice.payment_state, "reversed")
        self.assertNotIn(invoice, self.order._get_payable_invoices())
        self.assertFalse(self.order._is_fully_paid())

    def test_no_sale_order_is_refused(self):
        bastk = self._bastk(order=self.env["sale.order"])
        with self.assertRaisesRegex(ValidationError, "tidak memiliki SO Reference"):
            bastk.action_submit_outside()

    def test_type_without_the_checklist_is_not_checked(self):
        bastk = self._bastk(bastk_type=self.free_type)
        bastk.action_submit_outside()
        self.assertEqual(bastk.state, "submitted_outside")

    def test_form_of_the_bastk_type_shows_both_checklists(self):
        arch = etree.fromstring(self.env["bastk.type"].get_view(view_type="form")["arch"])
        self.assertFalse(arch.xpath("//field[@name='is_disposal']")[0].get("invisible"))
        self.assertEqual(arch.xpath("//field[@name='require_invoice_paid']")[0].get("invisible"), "not need_submit_out")

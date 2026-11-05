from lxml import etree

from odoo import fields
from odoo.tests import tagged
from odoo.tools.safe_eval import safe_eval

from odoo.addons.x_disposal.tests.test_disposal_aging import DisposalFlowCommon


@tagged("post_install", "-at_install")
class TestDisposalReport(DisposalFlowCommon):

    def _shown(self, bidding):
        action = self.env.ref("x_disposal_reporting.action_disposal_reporting")
        self.env.flush_all()
        return bidding in self.env["disposal.bidding"].search(safe_eval(action.domain))

    def _bidding(self, state="draft"):
        return self.env["disposal.bidding"].create({"vehicle_id": self.vehicle.id, "state": state})

    def test_columns_and_labels(self):
        view = self.env.ref("x_disposal_reporting.view_disposal_reporting_tree")
        arch = etree.fromstring(self.env["disposal.bidding"].get_view(view.id, "list")["arch"])
        columns = arch.xpath("//list/field")
        self.assertEqual((columns[0].get("name"), columns[0].get("string")), ("name", "Bidding Number"))
        labels = {column.get("name"): column.get("string") for column in columns}
        self.assertEqual(labels["start_date"], "Start Date Bidding")
        self.assertEqual(labels["end_date"], "End Date Bidding")
        self.assertEqual(labels["create_date"], "Created Date")
        self.assertEqual(labels["disposal_accum_depreciation"], "Akm. Depresiasi")
        self.assertIn("status_disposal_date", labels)
        self.assertEqual(self.env["disposal.bidding"]._fields["status_disposal_date"].string, "Status Disposal Date")

    def test_only_open_states_are_shown(self):
        for state, expected in (("draft", True), ("waiting_approval", True), ("approved", True), ("rejected", False)):
            self.assertEqual(self._shown(self._bidding(state)), expected, state)

    def test_bidding_leaves_the_report_once_its_sale_is_fully_paid(self):
        order = self._create_order()
        bidding = order.disposal_bidding_id
        bidding.state = "approved"
        self.assertTrue(self._shown(bidding))
        invoice = self._invoice(order)
        self.assertTrue(self._shown(bidding))
        self._pay(invoice, fields.Date.today(), reconciled=False)
        self.assertTrue(self._shown(bidding), "In Payment is not Paid yet")
        self._pay(invoice, fields.Date.today())
        self.assertFalse(self._shown(bidding))

    def test_sale_with_something_left_to_invoice_stays_in_the_report(self):
        order = self._create_order()
        bidding = order.disposal_bidding_id
        bidding.state = "approved"
        self._pay(self._invoice(order), fields.Date.today())
        self.assertFalse(self._shown(bidding))
        service = self.env["product.product"].create({"name": "Fee", "type": "service", "invoice_policy": "order"})
        self.env["sale.order.line"].create({"order_id": order.id, "product_id": service.id, "price_unit": 100})
        self.assertTrue(self._shown(bidding))

    def test_status_disposal_date_follows_the_change_of_status(self):
        bidding = self._bidding()
        self.assertFalse(bidding.status_disposal_date)
        self._move_to(self.disposal)
        self.assertEqual(bidding.status_disposal_date, fields.Date.context_today(self.vehicle))

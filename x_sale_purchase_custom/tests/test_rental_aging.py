from datetime import timedelta

from freezegun import freeze_time

from odoo import Command, fields
from odoo.tests import tagged

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestRentalAging(RentalBillingEngineInvoiceCommon):
    """Aging of a rental unit runs from Actual Delivery to today, or to its Return Date."""

    def setUp(self):
        super().setUp()
        self.today = fields.Date.context_today(self.env.user)

    def _line(self, days_out):
        return self._order(delivery=self.today - timedelta(days=days_out)).order_line

    def test_aging_counts_from_actual_delivery_until_today(self):
        self.assertEqual(self._line(5).rental_aging, 5)

    def test_aging_stops_at_the_return_date_and_runs_again_when_it_is_cleared(self):
        line = self._line(10)
        line.bastk_return_date = self.today - timedelta(days=3)
        self.assertEqual(line.rental_aging, 7)
        line.bastk_return_date = False
        self.assertEqual(line.rental_aging, 10)

    def test_no_aging_without_delivery_before_it_or_on_sales_orders(self):
        self.assertEqual(self._order(delivery=False).order_line.rental_aging, 0)
        self.assertEqual(self._line(-2).rental_aging, 0)
        sale = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [Command.create(self._line_values(self.today - timedelta(days=5)))],
        })
        self.assertFalse(sale.is_rental_order)
        self.assertEqual(sale.order_line.rental_aging, 0)

    def test_nightly_cron_ages_only_the_units_still_out(self):
        out, back = self._line(5), self._line(5)
        back.bastk_return_date = self.today
        cancelled = self._line(5)
        cancelled.order_id.state = 'cancel'
        self.assertEqual((out | back | cancelled).mapped('rental_aging'), [5, 5, 5])
        with freeze_time(self.today + timedelta(days=2)):
            self.env.ref('x_sale_purchase_custom.ir_cron_rental_aging').ir_actions_server_id.run()
        self.assertEqual(out.rental_aging, 7)
        self.assertEqual(back.rental_aging, 5)
        self.assertEqual(cancelled.rental_aging, 5)

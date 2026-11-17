from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTicketLeadTime(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env['helpdesk.ticket.category'].create({'name': 'Lead Time Test Category'})
        cls.tag = cls.env['helpdesk.tag'].create({'name': 'Lead Time Test Tag'})
        cls.today = fields.Date.context_today(cls.env['helpdesk.ticket'])

    def _ticket(self, days_ago):
        return self.env['helpdesk.ticket'].create({
            'ticket_category_id': self.category.id,
            'tag_ids': [(6, 0, self.tag.ids)],
            'tanggal_lapor': self.today - timedelta(days=days_ago),
        })

    def _age_one_day(self, ticket):
        """Simulate a night passing: the report date moves back without recomputing."""
        self.env.cr.execute(
            "UPDATE helpdesk_ticket SET tanggal_lapor = tanggal_lapor - 1 WHERE id = %s", (ticket.id,))
        ticket.invalidate_recordset(['tanggal_lapor', 'lead_time'])

    def test_running_ticket_counts_up_to_today(self):
        self.assertEqual(self._ticket(0).lead_time, 0)
        self.assertEqual(self._ticket(3).lead_time, 3)

    def test_cron_moves_running_ticket_forward(self):
        ticket = self._ticket(2)
        self._age_one_day(ticket)
        self.assertEqual(ticket.lead_time, 2)
        self.env['helpdesk.ticket'].cron_refresh_lead_time()
        self.assertEqual(ticket.lead_time, 3)

    def test_completed_ticket_stops_at_tanggal_selesai(self):
        ticket = self._ticket(5)
        ticket.write({'tanggal_selesai': self.today - timedelta(days=1)})
        self.assertEqual(ticket.lead_time, 4)
        self._age_one_day(ticket)
        self.env['helpdesk.ticket'].cron_refresh_lead_time()
        self.assertEqual(ticket.lead_time, 4, "a completed ticket is not refreshed by the cron")

from datetime import timedelta

from lxml import etree

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOverviewStageCounters(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Stage = cls.env['helpdesk.stage']
        cls.new, cls.assigned, cls.progress = Stage.create([
            {'name': 'New Overview Test', 'sequence': 900},
            {'name': 'Assigned Overview Test', 'sequence': 901},
            {'name': 'In Progress Overview Test', 'sequence': 902},
        ])
        cls.team = cls.env['helpdesk.team'].create({
            'name': 'Overview Test Team',
            'stage_ids': [(6, 0, (cls.progress | cls.new | cls.assigned).ids)],
        })
        cls.category = cls.env['helpdesk.ticket.category'].create({'name': 'Overview Test Category'})

    def _tickets(self, stage, count, **vals):
        return self.env['helpdesk.ticket'].create([{
            'team_id': self.team.id, 'stage_id': stage.id, 'ticket_category_id': self.category.id, **vals,
        } for _ in range(count)])

    def test_one_counter_per_team_stage_in_stage_order(self):
        self._tickets(self.new, 2)
        self._tickets(self.progress, 3)
        self.assertEqual(self.team.stage_ticket_counts, [
            {'id': self.new.id, 'name': self.new.name, 'count': 2},
            {'id': self.assigned.id, 'name': self.assigned.name, 'count': 0},
            {'id': self.progress.id, 'name': self.progress.name, 'count': 3},
        ])

    def test_counters_follow_the_stage_configuration(self):
        closed = self.env['helpdesk.stage'].create({'name': 'Closed Overview Test', 'sequence': 903})
        self.team.stage_ids = [(4, closed.id), (3, self.assigned.id)]
        self.team.invalidate_recordset(['stage_ticket_counts'])
        self.assertEqual([c['id'] for c in self.team.stage_ticket_counts], [self.new.id, self.progress.id, closed.id])

    def test_a_counter_opens_the_team_tickets_of_its_stage_without_the_open_filter(self):
        tickets = self._tickets(self.progress, 2)
        self._tickets(self.new, 1)
        action = self.team.action_view_stage_tickets(self.progress.id)
        self.assertEqual(self.env['helpdesk.ticket'].search(action['domain']), tickets)
        self.assertFalse(action['context']['search_default_is_open'])
        self.assertEqual(action['context']['default_team_id'], self.team.id)

    def test_tanggal_lapor_timeframe_filter(self):
        today = fields.Date.context_today(self.env.user)
        recent = self._tickets(self.new, 1, tanggal_lapor=today - timedelta(days=3))
        self._tickets(self.new, 1, tanggal_lapor=today - timedelta(days=40))
        arch = etree.fromstring(self.env['helpdesk.ticket'].get_view(view_type='search')['arch'])
        node = arch.xpath("//filter[@name='filter_tanggal_lapor']")[0]
        self.assertEqual(node.get('date'), 'tanggal_lapor')
        domain = [('team_id', '=', self.team.id), ('tanggal_lapor', '>=', 'today -30d +1d')]
        self.assertEqual(self.env['helpdesk.ticket'].search(domain), recent)

    def test_overview_shows_stage_row_and_alert_row(self):
        arch = etree.fromstring(self.env['helpdesk.team'].get_view(
            self.env.ref('helpdesk.helpdesk_team_kanban_view').id, 'kanban')['arch'])
        self.assertEqual(arch.xpath("//field[@name='stage_ticket_counts']")[0].get('widget'), 'helpdesk_stage_counters')
        self.assertTrue(arch.xpath("//a[@name='action_view_urgent']"))
        self.assertFalse(arch.xpath("//a[@name='action_view_open_ticket']"))
        self.assertFalse(arch.xpath("//field[@name='unassigned_tickets']"))

from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestComplaintDescription(TransactionCase):

    def _ticket(self, **vals):
        # The ticket title is built from its category.
        category = self.env['helpdesk.ticket.category'].create({'name': 'Complaint Test Category'})
        return self.env['helpdesk.ticket'].create({
            'ticket_category_id': category.id, 'tag_ids': [(0, 0, {'name': 'Complaint Test Tag'})], **vals,
        })

    def test_spk_from_ticket_takes_the_complaint(self):
        ticket = self._ticket(complaint_description='Rem berbunyi saat berhenti')
        context = ticket.action_create_spk()['context']
        self.assertEqual(context['default_description'], 'Rem berbunyi saat berhenti')

    def test_spk_from_ticket_without_complaint_starts_empty(self):
        context = self._ticket().action_create_spk()['context']
        self.assertFalse(context['default_description'])

    def test_spk_from_bak_takes_the_complaint_of_its_ticket(self):
        ticket = self._ticket(complaint_description='AC tidak dingin')
        bak = self.env['bak'].new({'helpdesk_ticket_id': ticket.id})
        context = bak.action_create_spk()['context']
        self.assertEqual(context['default_description'], 'AC tidak dingin')
        self.assertNotIn('default_description', self.env['bak'].new({}).action_create_spk()['context'])

    def test_complaint_sits_on_the_ticket_form(self):
        arch = etree.fromstring(self.env['helpdesk.ticket'].get_view(
            self.env.ref('helpdesk.helpdesk_ticket_view_form').id, 'form')['arch'])
        node = arch.xpath("//field[@name='complaint_description']")[0]
        self.assertEqual(node.get('readonly'), 'bak_reference_id or spk_reference_id')

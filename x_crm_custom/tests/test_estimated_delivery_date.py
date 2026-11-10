import ast
from datetime import date
from pathlib import Path

from lxml import etree

from odoo.tests import HttpCase, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCrmEstimatedDeliveryDate(TransactionCase):
    def test_view_uses_scoped_date_widget_and_keeps_stage_modifiers(self):
        view = self.env.ref('x_crm_custom.crm_lead_view_form_custom')
        node = etree.fromstring(view.arch_db).xpath('//field[@name="estimated_delivery"]')[0]
        self.assertEqual(node.get('widget'), 'crm_estimated_delivery_date')
        self.assertEqual(node.get('readonly'), "stage_name != 'Offering'")
        self.assertEqual(node.get('required'), "stage_name in ['Offering', 'Negotiation', 'Deal', 'Delivery']")
        self.assertFalse(node.get('options'))
        self.assertEqual(self.env['crm.lead']._fields['estimated_delivery'].type, 'date')
        manifest = ast.literal_eval((Path(__file__).parent.parent / '__manifest__.py').read_text())
        self.assertIn('x_crm_custom/static/src/js/estimated_delivery_date_field.js', manifest['assets']['web.assets_backend'])

    def test_stored_values_keep_iso_date_semantics_and_empty_dates(self):
        lead = self.env['crm.lead'].create({
            'name': 'CRM Estimated Delivery Date Test', 'estimated_delivery': '2026-02-01',
        })
        self.assertEqual(lead.estimated_delivery, date(2026, 2, 1))
        lead.estimated_delivery = '2024-02-29'
        lead.flush_recordset(['estimated_delivery'])
        lead.invalidate_recordset(['estimated_delivery'])
        self.assertEqual(lead.estimated_delivery, date(2024, 2, 29))
        lead.estimated_delivery = False
        self.assertFalse(lead.estimated_delivery)


@tagged('post_install', '-at_install')
class TestCrmEstimatedDeliveryBrowser(HttpCase):
    def test_estimated_delivery_widget_in_browser(self):
        # HOOT strips ../tests/ and the .test suffix when naming its suite.
        suite = '@x_crm_custom/estimated_delivery_date'
        suite_hash = 0
        for character in suite:
            suite_hash = ((suite_hash << 5) - suite_hash + ord(character)) & 0xFFFFFFFF
        self.browser_js(
            '/web/tests?headless&loglevel=2&preset=desktop&timeout=15000'
            f'&id={suite_hash:08x}',
            '', login='admin', timeout=180,
            success_signal='[HOOT] Test suite succeeded',
            error_checker=lambda message: '[HOOT]' not in message,
        )

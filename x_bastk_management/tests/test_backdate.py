from datetime import timedelta

from lxml import etree

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBastkBackdate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'QA BASTK Customer'})
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'QA BASTK Brand'})
        cls.model = cls.env['fleet.vehicle.model'].create({'name': 'QA BASTK Model', 'brand_id': brand.id})
        cls.bastk_type = cls.env['bastk.type'].create({
            'name': 'QA Backdate', 'need_submit_out': True, 'need_submit_in': True,
            'need_gi': False, 'need_gr': False,
        })

    def _bastk(self, **values):
        vehicle = self.env['fleet.vehicle'].create({'model_id': self.model.id})
        return self.env['bastk.management'].create({
            'bastk_type_id': self.bastk_type.id, 'partner_id': self.partner.id,
            'vehicle_id': vehicle.id,
            'line_keluar_ids': [Command.create({'name': 'QA Checklist Out', 'condition_baik': True, 'bastk_type': 'keluar'})],
            'line_masuk_ids': [Command.create({'name': 'QA Checklist In', 'condition_baik': True, 'bastk_type': 'masuk'})],
            **values,
        })

    def _wizard(self, bastk, direction, date):
        return self.env['bastk.submit.wizard'].create({
            'bastk_id': bastk.id, 'submit_type': direction,
            'pic': 'QA PIC', 'call_number': '0800000000', 'odometer': 0, 'date': date,
        })

    def test_create_and_edit_past_dates(self):
        today = fields.Date.context_today(self.env['bastk.management'])
        record = self._bastk(start_date=today - timedelta(days=30), end_date=today - timedelta(days=10))
        record.write({'start_date': today - timedelta(days=31), 'end_date': today - timedelta(days=11)})
        self.assertEqual(record.start_date, today - timedelta(days=31))
        self.assertEqual(record.end_date, today - timedelta(days=11))

    def test_backdated_end_date_after_submit_out(self):
        today = fields.Date.context_today(self.env['bastk.management'])
        record = self._bastk(start_date=today - timedelta(days=30))
        record.state = 'submitted_outside'
        record.end_date = today - timedelta(days=5)
        self.assertEqual(record.end_date, today - timedelta(days=5))

    def test_invalid_date_order_still_rejected_on_create_and_write(self):
        today = fields.Date.context_today(self.env['bastk.management'])
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._bastk(start_date=today - timedelta(days=3), end_date=today - timedelta(days=4))
        record = self._bastk(start_date=today - timedelta(days=3))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            record.end_date = today - timedelta(days=4)

    def test_wizard_defaults_keep_existing_past_dates(self):
        today = fields.Date.context_today(self.env['bastk.management'])
        record = self._bastk(start_date=today - timedelta(days=30), end_date=today - timedelta(days=5))
        for direction, date in [('out', record.start_date), ('in', record.end_date)]:
            values = self.env['bastk.submit.wizard'].with_context(
                active_model='bastk.management', active_id=record.id, default_submit_type=direction,
            ).default_get(['bastk_id', 'submit_type', 'date', 'pic', 'call_number', 'odometer'])
            self.assertEqual(fields.Date.to_date(values['date']), date)

    def test_wizard_backdated_submit_out_and_in(self):
        today = fields.Date.context_today(self.env['bastk.management'])
        record = self._bastk(**{
            'customer_sign_keluar': 'c2lnbg==', 'cakrawala_sign_keluar': 'c2lnbg==',
            'customer_name_keluar': 'QA Customer', 'cakrawala_name_keluar': 'QA Company',
            'customer_sign_masuk': 'c2lnbg==', 'cakrawala_sign_masuk': 'c2lnbg==',
            'customer_name_masuk': 'QA Customer', 'cakrawala_name_masuk': 'QA Company',
        })
        self._wizard(record, 'out', today - timedelta(days=30)).action_confirm()
        self.assertEqual(record.state, 'submitted_outside')
        self.assertEqual(record.start_date, today - timedelta(days=30))
        self._wizard(record, 'in', today - timedelta(days=5)).action_confirm()
        self.assertEqual(record.state, 'submitted_inside')
        self.assertEqual(record.end_date, today - timedelta(days=5))
        self.assertEqual(record.aging, 25)

    def test_wizard_invalid_order_still_rejected(self):
        today = fields.Date.context_today(self.env['bastk.management'])
        record = self._bastk(start_date=today - timedelta(days=5), end_date=today - timedelta(days=2))
        for direction, date in [('in', today - timedelta(days=6)), ('out', today - timedelta(days=1))]:
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self._wizard(record, direction, date).action_confirm()

    def test_signature_requirement_not_disabled(self):
        today = fields.Date.context_today(self.env['bastk.management'])
        record = self._bastk()
        with self.assertRaisesRegex(ValidationError, 'Signature'), self.cr.savepoint():
            self._wizard(record, 'out', today - timedelta(days=5)).action_confirm()

    def test_date_picker_has_no_today_minimum(self):
        for model, xmlid, field in [
            ('bastk.management', 'x_bastk_management.view_bastk_form', 'start_date'),
            ('bastk.submit.wizard', 'x_bastk_management.view_bastk_submit_wizard_form', 'date'),
        ]:
            view = self.env.ref(xmlid, raise_if_not_found=False)
            if not view:
                view = self.env['ir.ui.view'].search([('model', '=', model), ('type', '=', 'form')], limit=1)
            arch = etree.fromstring(self.env[model].get_view(view_id=view.id, view_type='form')['arch'])
            nodes = arch.xpath("//field[@name='%s']" % field)
            self.assertTrue(nodes)
            for node in nodes:
                self.assertNotIn('min_date', node.get('options', ''))

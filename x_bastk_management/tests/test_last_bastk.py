from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLastBastk(TransactionCase):
    """Latest BASTK and its status on the vehicle, and BASTK state changes that refresh them."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'QA Last BASTK Customer'})
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'QA Last BASTK Brand'})
        cls.model = cls.env['fleet.vehicle.model'].create({'name': 'QA Last BASTK Model', 'brand_id': brand.id})
        cls.bastk_type = cls.env['bastk.type'].create({
            'name': 'QA Last BASTK', 'need_submit_out': True, 'need_submit_in': True,
            'need_gi': False, 'need_gr': False,
        })
        cls.sub_status = cls.env['vehicle.substatus'].create({'name': 'QA Last BASTK Sub-Status'})
        cls.vehicle = cls.env['fleet.vehicle'].create({'model_id': cls.model.id})

    def _bastk(self):
        return self.env['bastk.management'].create({
            'bastk_type_id': self.bastk_type.id, 'partner_id': self.partner.id, 'vehicle_id': self.vehicle.id,
            'start_date': fields.Date.context_today(self.vehicle),
            'line_keluar_ids': [Command.create({'name': 'QA Out', 'condition_baik': True, 'bastk_type': 'keluar'})],
            'line_masuk_ids': [Command.create({'name': 'QA In', 'condition_baik': True, 'bastk_type': 'masuk'})],
            'customer_sign_keluar': 'iVBORw0KGgo=', 'customer_name_keluar': 'QA Customer',
            'cakrawala_sign_keluar': 'iVBORw0KGgo=', 'cakrawala_name_keluar': 'QA Cakrawala',
        })

    def test_latest_bastk_and_status_follow_the_newest_bastk(self):
        first = self._bastk()
        self.assertEqual(self.vehicle.last_bastk_id, first)
        self.assertEqual(self.vehicle.last_bastk_state, 'draft')
        first.state = 'submitted_outside'
        self.assertEqual(self.vehicle.last_bastk_state, 'submitted_outside')
        first.state = 'done'
        self.assertEqual(self.vehicle.last_bastk_state, 'done')
        second = self._bastk()
        self.assertEqual(self.vehicle.last_bastk_id, second)
        self.assertEqual(self.vehicle.last_bastk_state, 'draft')

    def test_bastk_state_changes_after_the_status_was_read_in_the_same_transaction(self):
        bastk = self._bastk()
        # The vehicle form, a status change or its chatter read the latest status first.
        self.assertEqual(self.vehicle.last_bastk_state, 'draft')
        bastk.state = 'submitted_outside'
        self.assertEqual(self.vehicle.last_bastk_state, 'submitted_outside')

    def test_vehicle_change_then_submit_out_in_one_call(self):
        """A Replacement Car Goods Issue changes the vehicle sub-status before Submit Out sets the state."""
        bastk = self._bastk()
        self.env.invalidate_all()
        self.vehicle._set_fleet_status(sub_status=self.sub_status)
        wizard = self.env['bastk.submit.wizard'].create({
            'bastk_id': bastk.id, 'submit_type': 'out', 'pic': 'QA PIC', 'call_number': '0800000000',
            'odometer': 0, 'date': bastk.start_date,
        })
        wizard.action_confirm()
        self.assertEqual(bastk.state, 'submitted_outside')
        self.assertEqual(self.vehicle.last_bastk_state, 'submitted_outside')

    def test_latest_status_is_not_logged_in_the_vehicle_chatter(self):
        self.assertFalse(getattr(self.vehicle._fields['last_bastk_state'], 'tracking', False))
        self.assertNotIn('last_bastk_state', self.vehicle._track_get_fields())

from lxml import etree

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestFleetLock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sold = cls.env.ref('x_stock_asset_receipt.vehicle_substatus_sold')
        cls.short_term = cls.env.ref('x_stock_asset_receipt.vehicle_substatus_short_term')
        cls.inactive = cls.sold.state_id
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'Lock Brand'})
        model = cls.env['fleet.vehicle.model'].create({'name': 'Lock Model', 'brand_id': brand.id})
        cls.vehicle = cls.env['fleet.vehicle'].create({
            'model_id': model.id,
            'license_plate': 'B 9 LOCK',
            'fleet_sub_status_id': cls.short_term.id,
            'state_id': cls.short_term.state_id.id,
        })
        cls.spk = cls.env['fleet.spk'].create({
            'vehicle_id': cls.vehicle.id,
            'category': 'internal',
            'description': 'Lock test',
        })
        cls.admin = new_test_user(
            cls.env, login='lock_admin', groups='base.group_system,fleet.fleet_group_manager,stock.group_stock_user',
        )
        cls.officer = new_test_user(cls.env, login='lock_officer', groups='fleet.fleet_group_user')
        cls.vehicle._set_fleet_status(sub_status=cls.sold)

    def _import_status(self, user, sub_status):
        return self.vehicle.with_user(user).with_context(import_file=True).write({
            'fleet_sub_status_id': sub_status.id,
            'state_id': sub_status.state_id.id,
        })

    def test_lock_follows_sub_status_flag_not_inactive_status(self):
        self.assertTrue(self.vehicle.is_fleet_locked)
        self.assertTrue(self.spk.is_fleet_locked)
        unflagged = self.env['vehicle.substatus'].create({'name': 'Inactive Open', 'state_id': self.inactive.id})
        self._import_status(self.admin, unflagged)
        self.assertEqual(self.vehicle.state_id, self.inactive)
        self.assertFalse(self.vehicle.is_fleet_locked)
        self.assertFalse(self.spk.is_fleet_locked)

    def test_status_cannot_be_changed_outside_import_even_by_administrator(self):
        vehicle = self.vehicle.with_user(self.admin)
        for vals in (
            {'fleet_sub_status_id': self.short_term.id},
            {'state_id': self.short_term.state_id.id},
            {'active': False},
            {'license_plate': 'B 1 X'},
        ):
            with self.assertRaises(UserError):
                vehicle.write(vals)

    def test_superuser_code_cannot_change_status_but_may_repeat_it(self):
        with self.assertRaises(UserError):
            self.vehicle.sudo().write({'state_id': self.short_term.state_id.id})
        self.vehicle.sudo()._set_fleet_status(sub_status=self.sold)
        self.vehicle.sudo()._set_fleet_status(state=self.inactive)
        self.assertEqual(self.vehicle.fleet_sub_status_id, self.sold)

    def test_import_is_for_fleet_administrators_and_status_only(self):
        with self.assertRaises(UserError):
            self._import_status(self.officer, self.short_term)
        with self.assertRaises(UserError):
            self.vehicle.with_user(self.admin).with_context(import_file=True).write({'license_plate': 'B 1 X'})
        self._import_status(self.admin, self.short_term)
        self.assertFalse(self.vehicle.is_fleet_locked)
        self.spk.with_user(self.admin).write({'description': 'Open again'})

    def _excel_roundtrip(self, user, fields, row):
        """Export the vehicle's External ID, then import the edited row as a file."""
        external_id = self.vehicle.with_context(import_compat=True).export_data(['id'])['datas'][0][0]
        content = ','.join(['id'] + fields) + '\n' + ','.join([external_id] + row) + '\n'
        wizard = self.env['base_import.import'].with_user(user).create({
            'res_model': 'fleet.vehicle',
            'file': content.encode(),
            'file_type': 'text/csv',
        })
        return wizard.execute_import(
            ['id'] + fields, ['id'] + fields,
            {'quoting': '"', 'separator': ',', 'has_headers': True},
        )

    def test_export_import_corrects_status_of_a_sold_vehicle(self):
        result = self._excel_roundtrip(
            self.admin, ['state_id', 'fleet_sub_status_id'],
            [self.short_term.state_id.name, self.short_term.name],
        )
        self.assertFalse(result['messages'])
        self.assertEqual(self.vehicle.fleet_sub_status_id, self.short_term)
        self.assertFalse(self.vehicle.is_fleet_locked)

    def test_export_import_refuses_other_fields_and_other_users(self):
        result = self._excel_roundtrip(self.admin, ['license_plate'], ['B 1 X'])
        self.assertTrue(result['messages'])
        self.assertEqual(self.vehicle.license_plate, 'B 9 LOCK')
        result = self._excel_roundtrip(
            self.officer, ['state_id', 'fleet_sub_status_id'],
            [self.short_term.state_id.name, self.short_term.name],
        )
        self.assertTrue(result['messages'])
        self.assertEqual(self.vehicle.fleet_sub_status_id, self.sold)

    def test_related_record_is_read_only(self):
        spk = self.spk.with_user(self.admin)
        with self.assertRaises(UserError):
            spk.write({'description': 'Changed'})
        with self.assertRaises(UserError):
            spk.action_done()
        with self.assertRaises(UserError):
            spk.unlink()
        with self.assertRaises(UserError):
            self.env['fleet.spk'].with_user(self.admin).create({
                'vehicle_id': self.vehicle.id,
                'category': 'internal',
                'description': 'New on a sold unit',
            })

    def test_chatter_stays_available(self):
        self.spk.with_user(self.admin).message_post(body='Note on a sold unit')
        self.vehicle.with_user(self.admin).message_post(body='Note on a sold unit')

    def _submit_bastk(self, bastk_type):
        bastk = self.env['bastk.management'].with_user(self.admin).with_context(skip_submit_wizard=True).create({
            'bastk_type_id': bastk_type.id,
            'partner_id': self.admin.partner_id.id,
            'vehicle_id': self.vehicle.id,
        })
        bastk.sudo().line_keluar_ids.filtered(lambda line: not line.display_type).write({'condition_baik': True})
        if not bastk.sudo().line_keluar_ids.filtered(lambda line: not line.display_type):
            self.env['bastk.description'].create({
                'bastk_id': bastk.id, 'bastk_type': 'keluar', 'name': 'Unit', 'condition_baik': True,
            })
        bastk.sudo().write({
            'customer_sign_keluar': 'eA==', 'customer_name_keluar': 'Buyer',
            'cakrawala_sign_keluar': 'eA==', 'cakrawala_name_keluar': 'Cakrawala',
            'pic_keluar': 'PIC', 'call_number_keluar': '0812',
            'start_date': fields.Date.context_today(bastk), 'odometer_out': 500,
        })
        return bastk

    def test_disposal_bastk_finishes_after_the_unit_is_sold(self):
        bastk_type = self.env['bastk.type'].create({
            'name': 'Disposal Lock', 'is_disposal': True, 'need_submit_out': True, 'need_submit_in': False,
            'out_substate_id': self.sold.id, 'out_state_id': self.inactive.id,
        })
        bastk = self._submit_bastk(bastk_type)
        self.assertFalse(bastk.is_fleet_locked)
        bastk.action_submit_outside()
        self.assertEqual(bastk.state, 'submitted_outside')
        self.assertEqual(self.vehicle.odometer, 500)
        # Two clicks are two requests: nothing stays in cache between them.
        self.env.invalidate_all()
        bastk.action_done()
        self.assertEqual(bastk.state, 'done')
        self.assertEqual(self.vehicle.fleet_sub_status_id, self.sold)
        self.assertTrue(self.vehicle.is_fleet_locked)

    def test_regular_bastk_is_refused_on_a_sold_unit(self):
        bastk_type = self.env['bastk.type'].create({'name': 'Regular Lock', 'need_submit_in': False})
        with self.assertRaises(UserError):
            self._submit_bastk(bastk_type)

    def _new_bastk_form(self):
        """The form Create BASTK opens on the delivery of a sold unit, its type still empty."""
        return Form(self.env['bastk.management'].with_user(self.admin).with_context(
            default_vehicle_id=self.vehicle.id, default_partner_id=self.admin.partner_id.id,
        ))

    def _disposal_type(self):
        return self.env['bastk.type'].create({
            'name': 'Disposal Lock', 'is_disposal': True, 'need_submit_out': True, 'need_submit_in': False,
            'out_substate_id': self.sold.id, 'out_state_id': self.inactive.id,
        })

    def test_disposal_type_can_be_chosen_on_the_form_of_a_sold_unit(self):
        form = self._new_bastk_form()
        self.assertFalse(form.is_fleet_locked)
        form.bastk_type_id = self._disposal_type()
        bastk = form.save()
        self.assertTrue(bastk.is_disposal)
        self.assertFalse(bastk.is_fleet_locked)

    def test_regular_type_chosen_on_the_form_is_refused_on_save(self):
        form = self._new_bastk_form()
        form.bastk_type_id = self.env['bastk.type'].create({'name': 'Regular Lock', 'need_submit_in': False})
        with self.assertRaisesRegex(UserError, 'is Sold'):
            form.save()

    def test_disposal_bastk_cannot_become_a_regular_one_on_a_sold_unit(self):
        form = self._new_bastk_form()
        form.bastk_type_id = self._disposal_type()
        bastk = form.save()
        regular = self.env['bastk.type'].create({'name': 'Regular Lock', 'need_submit_in': False})
        with self.assertRaisesRegex(UserError, 'is Sold'):
            bastk.write({'bastk_type_id': regular.id})

    def test_saved_regular_bastk_stays_locked_once_its_unit_is_sold(self):
        self._import_status(self.admin, self.short_term)
        bastk = self.env['bastk.management'].with_user(self.admin).create({
            'bastk_type_id': self.env['bastk.type'].create({'name': 'Regular Lock', 'need_submit_in': False}).id,
            'partner_id': self.admin.partner_id.id,
            'vehicle_id': self.vehicle.id,
        })
        self.assertFalse(bastk.is_fleet_locked)
        self.vehicle.sudo()._set_fleet_status(sub_status=self.sold)
        self.env.invalidate_all()
        self.assertTrue(bastk.is_fleet_locked)

    def test_apply_new_driver_is_hidden_and_refused(self):
        arch = etree.fromstring(self.env['fleet.vehicle'].with_user(self.admin).get_view(view_type='form')['arch'])
        button = arch.xpath("//button[@name='action_accept_driver_change']")[0]
        self.assertIn('is_fleet_locked', button.get('invisible'))
        partner = self.env['res.partner'].create({'name': 'Future Driver'})
        self.env.cr.execute('UPDATE fleet_vehicle SET future_driver_id=%s WHERE id=%s', (partner.id, self.vehicle.id))
        self.vehicle.invalidate_recordset()
        with self.assertRaises(UserError):
            self.vehicle.with_user(self.admin).action_accept_driver_change()

    def test_only_print_and_smart_buttons_stay_on_locked_forms(self):
        for model in ('fleet.vehicle', 'fleet.vehicle.log.contract', 'fleet.spk', 'bak', 'bastk.management',
                      'replacement.car', 'service.planning', 'disposal.bidding'):
            arch = etree.fromstring(self.env[model].with_user(self.admin).get_view(view_type='form')['arch'])
            for button in arch.xpath("//button[@type='object'][not(ancestor::field)]"):
                invisible = button.get('invisible') or ''
                if 'oe_stat_button' in (button.get('class') or '') or 'print' in button.get('name') \
                        or invisible in ('1', 'True', 'true'):
                    continue
                self.assertIn('is_fleet_locked', invisible, '%s: %s' % (model, button.get('name')))

    def test_read_only_fields_are_not_made_editable_on_unlocked_forms(self):
        for name in ('fleet.vehicle', 'fleet.spk', 'bak', 'bastk.management', 'disposal.bidding'):
            model = self.env[name].with_user(self.admin)
            arch = etree.fromstring(model.get_view(view_type='form')['arch'])
            for node in arch.xpath("//field[not(ancestor::field)][@readonly='is_fleet_locked']"):
                field = model._fields.get(node.get('name'))
                self.assertFalse(field is not None and field.readonly, '%s: %s' % (name, node.get('name')))

    def test_form_is_read_only_and_keeps_print_button(self):
        arch = etree.fromstring(self.env['fleet.spk'].with_user(self.admin).get_view(view_type='form')['arch'])
        self.assertIn('is_fleet_locked', arch.xpath("//field[@name='vehicle_id']")[0].get('readonly'))
        self.assertIn('is_fleet_locked', arch.xpath("//button[@name='action_done']")[0].get('invisible'))
        self.assertNotIn('is_fleet_locked', arch.xpath("//button[@name='action_print_out']")[0].get('invisible') or '')

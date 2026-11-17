from datetime import date, datetime
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from lxml import etree

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRentalOrderReplacementCar(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={**cls.env.context, 'tracking_disable': True, 'tz': 'Asia/Jakarta'})
        cls.partner = cls.env['res.partner'].create({'name': 'RC Rental Test Customer'})
        cls.product = cls.env['product.product'].create({
            'name': 'RC Rental Test Vehicle', 'type': 'consu', 'rent_ok': True,
            'list_price': 3000000, 'taxes_id': [Command.clear()],
        })
        region = cls.env['rpc.wilayah'].create({'name': 'RC Test Region'})
        province = cls.env['rpc.provinsi'].create({'name': 'RC Test Province', 'wilayah_id': region.id})
        cls.city = cls.env['rpc.kota'].create({'name': 'RC Test City', 'provinsi_id': province.id})
        cls.rental_type = cls.env['sale.rental.type'].create({'name': 'RC Test Rental'})
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'RC Test Brand'})
        model = cls.env['fleet.vehicle.model'].create({'name': 'RC Test Model', 'brand_id': brand.id})
        # A plain rental unit: not in the Replacement Car pool and not in stock.
        cls.unit = cls.env['fleet.vehicle'].create({
            'model_id': model.id, 'license_plate': 'B 11 RCO', 'initial_license_plate': 'B 11 RCO',
            'asset_number': 'RCO-B11',
        })

    def _order(self, lines):
        start = datetime(2026, 11, 20, 3)
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_rental_order': True,
            'rental_type_id': self.rental_type.id,
            'attention_up': 'RC Test PIC',
            'location_id': self.city.id,
            'rental_start_date': start,
            'rental_return_date': start + relativedelta(months=3),
            'actual_rental_start_date': start,
            'masa_sewa_bulan': 3,
            'state': 'sale',
            'order_line': [Command.create({
                'product_id': self.product.id, 'product_uom_qty': 1, 'price_unit': 3000000,
                'tax_ids': [Command.clear()], **values,
            }) for values in lines],
        })

    def test_one_rc_per_ticked_line_with_the_line_unit_as_replacement(self):
        order = self._order([{}, {'is_pdu_rc': True, 'fleet_vehicle_id': self.unit.id}, {'is_pdu_rc': True}])
        self.assertTrue(order.can_create_replacement_car)
        order.action_create_replacement_car()

        cars = order.replacement_car_ids
        self.assertEqual(len(cars), 2)
        self.assertEqual(order.replacement_car_count, 2)
        self.assertEqual(cars.rental_order_line_id, order.order_line.filtered('is_pdu_rc'))
        self.assertEqual(cars.rental_order_id, order)
        with_unit = cars.filtered(lambda rc: rc.rental_order_line_id.fleet_vehicle_id)
        self.assertEqual(with_unit.vehicle_new_id, self.unit)
        self.assertFalse((cars - with_unit).vehicle_new_id)
        for rc in cars:
            self.assertEqual(rc.state, 'draft')
            self.assertEqual(rc.customer_id, self.partner)
            self.assertFalse(rc.vehicle_old_id)
            self.assertEqual(rc.pic_name, 'RC Test PIC')
            self.assertEqual(rc.estimation_use_date, date(2026, 11, 20))

        self.assertFalse(order.can_create_replacement_car)
        with self.assertRaises(UserError):
            order.action_create_replacement_car()

    def test_a_rejected_rc_or_a_newly_ticked_line_allows_another_rc(self):
        order = self._order([{'is_pdu_rc': True}, {}])
        order.action_create_replacement_car()
        first = order.replacement_car_ids

        order.order_line.filtered(lambda l: not l.is_pdu_rc).is_pdu_rc = True
        self.assertTrue(order.can_create_replacement_car)
        order.action_create_replacement_car()
        self.assertEqual(len(order.replacement_car_ids), 2)

        first.state = 'rejected'
        self.assertTrue(order.can_create_replacement_car)
        order.action_create_replacement_car()
        self.assertEqual(len(order.replacement_car_ids), 3)

    def test_no_rc_button_before_confirmation(self):
        order = self._order([{'is_pdu_rc': True}])
        order.state = 'draft'
        self.assertFalse(order.can_create_replacement_car)

    def test_an_rc_from_a_rental_order_is_not_held_to_the_replacement_pool(self):
        order = self._order([{'is_pdu_rc': True, 'fleet_vehicle_id': self.unit.id}])
        order.action_create_replacement_car()
        rc = order.replacement_car_ids
        self._approve(rc)
        self.assertEqual(rc.state, 'approved')
        self.assertEqual(rc.vehicle_new_id, self.unit)

    # --- BASTK RO linked through RO + order line -------------------------------------------

    def _bastk_ro(self, vehicle, line, **values):
        """A BASTK RO of ``vehicle``, whose delivery move belongs to ``line``."""
        bastk_type = self.env['bastk.type'].create({
            'name': 'RC RO Test Type', 'need_submit_out': False, 'need_submit_in': False,
        })
        moves = self.env['stock.move'].new({'sale_line_id': line.id})
        Bastk = type(self.env['bastk.management'])
        with patch.object(Bastk, '_get_rental_unit_moves', lambda bastk: moves if bastk.vehicle_id == vehicle else bastk.env['stock.move']):
            return self.env['bastk.management'].create({
                'bastk_type_id': bastk_type.id, 'partner_id': self.partner.id,
                'vehicle_id': vehicle.id, 'sale_order_id': line.order_id.id, **values,
            })

    def _approve(self, rc):
        rc.vehicle_old_id = self.broken
        self.env['master.approval'].search([]).unlink()
        self.env['master.approval'].create({'sequence': 1, 'approver_id': self.env.user.id})
        rc.action_submit()
        rc.action_approve()

    @classmethod
    def _second_unit(cls):
        return cls.env['fleet.vehicle'].create({
            'model_id': cls.unit.model_id.id, 'license_plate': 'B 13 RCO',
            'initial_license_plate': 'B 13 RCO', 'asset_number': 'RCO-B13',
        })

    def setUp(self):
        super().setUp()
        self.broken = self.env['fleet.vehicle'].create({
            'model_id': self.unit.model_id.id, 'license_plate': 'B 12 RCO',
            'initial_license_plate': 'B 12 RCO', 'asset_number': 'RCO-B12',
        })

    def test_each_rc_follows_the_bastk_of_its_own_line(self):
        other_unit = self._second_unit()
        order = self._order([{'is_pdu_rc': True}, {'is_pdu_rc': True}])
        first_line, second_line = order.order_line
        order.action_create_replacement_car()
        first_rc = order.replacement_car_ids.filtered(lambda rc: rc.rental_order_line_id == first_line)
        second_rc = order.replacement_car_ids - first_rc

        # Same RO on both BASTK: only the order line tells them apart.
        bastk = self._bastk_ro(other_unit, second_line)
        self.assertEqual(bastk.replacement_car_id, second_rc)
        self.assertEqual(second_rc.vehicle_new_id, other_unit)
        self.assertFalse(first_rc.bastk_ids)
        self.assertFalse(first_rc.vehicle_new_id)

        self._approve(second_rc)
        self.assertEqual(second_rc.state, 'approved')
        bastk.write({'state': 'submitted_outside', 'start_date': date(2026, 11, 21)})
        self.assertEqual(second_rc.state, 'running')
        self.assertEqual(second_rc.bastk_out_id, bastk)
        bastk.write({'state': 'done', 'end_date': date(2026, 11, 25)})
        self.assertEqual(second_rc.state, 'done')
        self.assertEqual(second_rc.bastk_duration_days, 4)

    def test_an_rc_made_after_the_unit_left_links_and_runs_on_approval(self):
        order = self._order([{'is_pdu_rc': True}])
        line = order.order_line
        bastk = self._bastk_ro(self.unit, line, state='submitted_outside', start_date=date(2026, 11, 21))
        self.assertFalse(bastk.replacement_car_id)

        Bastk = type(self.env['bastk.management'])
        moves = self.env['stock.move'].new({'sale_line_id': line.id})
        with patch.object(type(self.env['replacement.car']), '_link_rental_order_bastks',
                             lambda rcs: bastk.with_env(rcs.env)._link_rental_order_replacement_car()), \
                patch.object(Bastk, '_get_rental_unit_moves', lambda b: moves):
            order.action_create_replacement_car()
        rc = order.replacement_car_ids
        self.assertEqual(bastk.replacement_car_id, rc)
        self.assertEqual(rc.vehicle_new_id, self.unit)
        self.assertEqual(rc.state, 'draft')

        self._approve(rc)
        self.assertEqual(rc.state, 'running')

    def test_an_rc_from_a_rental_order_makes_no_bastk_of_its_own(self):
        order = self._order([{'is_pdu_rc': True}])
        order.action_create_replacement_car()
        rc = order.replacement_car_ids
        self._approve(rc)
        self.assertEqual(rc.state, 'approved')
        with self.assertRaises(ValidationError):
            rc.action_create_bastk()
        arch = etree.fromstring(self.env['replacement.car'].get_view(view_type='form')['arch'])
        button = arch.xpath("//button[@name='action_create_bastk']")[0]
        self.assertIn('rental_order_line_id', button.get('invisible'))
        unit = arch.xpath("//field[@name='vehicle_new_id']")[0]
        self.assertIn('rental_order_line_id', unit.get('readonly'))

    def test_the_bastk_of_a_regular_rc_keeps_its_rc(self):
        order = self._order([{'is_pdu_rc': True}])
        order.action_create_replacement_car()
        regular = self.env['replacement.car'].create({
            'vehicle_old_id': self.broken.id, 'pic_name': 'PIC', 'estimation_use_date': date(2026, 11, 20),
        })
        bastk = self._bastk_ro(self.unit, order.order_line, replacement_car_id=regular.id)
        self.assertEqual(bastk.replacement_car_id, regular)

    def test_views_show_the_button_and_the_reference(self):
        arch = etree.fromstring(self.env['sale.order'].get_view(
            self.env.ref('sale_renting.rental_order_primary_form_view').id, 'form')['arch'])
        button = arch.xpath("//button[@name='action_create_replacement_car']")
        self.assertTrue(button)
        self.assertEqual(button[0].get('invisible'), 'not can_create_replacement_car')
        rc_arch = etree.fromstring(self.env['replacement.car'].get_view(view_type='form')['arch'])
        self.assertTrue(rc_arch.xpath("//field[@name='rental_order_id']"))

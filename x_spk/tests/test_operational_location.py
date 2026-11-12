import importlib.util

from odoo.exceptions import ValidationError
from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged


def _migration():
    path = '%s/migrations/19.0.1.6.5/post-migrate.py' % get_module_path('x_spk')
    spec = importlib.util.spec_from_file_location('x_spk_operational_location_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install')
class TestOperationalLocation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        wilayah = cls.env['rpc.wilayah'].search([], limit=1)
        cls.central_java = cls.env['rpc.provinsi'].create({'name': 'Test Jawa Tengah', 'wilayah_id': wilayah.id})
        cls.west_java = cls.env['rpc.provinsi'].create({'name': 'Test Jawa Barat', 'wilayah_id': wilayah.id})
        cls.boyolali = cls.env['rpc.kota'].create({'name': 'Boyolali', 'provinsi_id': cls.central_java.id})
        cls.bekasi_city = cls.env['rpc.kota'].create({'name': 'Kota Bekasi', 'provinsi_id': cls.west_java.id})
        cls.bekasi_regency = cls.env['rpc.kota'].create({'name': 'Kab. Bekasi', 'provinsi_id': cls.west_java.id})
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'Location Brand'})
        cls.model = cls.env['fleet.vehicle.model'].create({'name': 'Location Model', 'brand_id': brand.id})

    def test_picking_a_city_fills_its_province(self):
        vehicle = self.env['fleet.vehicle'].new({'model_id': self.model.id, 'operational_city_id': self.boyolali.id})
        vehicle._onchange_operational_city_id()
        self.assertEqual(vehicle.operational_province_id, self.central_java)

    def test_changing_the_province_clears_a_city_outside_it(self):
        vehicle = self.env['fleet.vehicle'].new({
            'model_id': self.model.id,
            'operational_city_id': self.boyolali.id,
            'operational_province_id': self.west_java.id,
        })
        vehicle._onchange_operational_province_id()
        self.assertFalse(vehicle.operational_city_id)

    def test_city_must_belong_to_the_province(self):
        vehicle = self.env['fleet.vehicle'].create({'model_id': self.model.id, 'license_plate': 'AD 1 LOC'})
        vehicle.write({'operational_city_id': self.boyolali.id, 'operational_province_id': self.central_java.id})
        with self.assertRaisesRegex(ValidationError, 'Boyolali'):
            vehicle.write({'operational_province_id': self.west_java.id})

    def test_the_dropdowns_cannot_create_master_data(self):
        arch = self.env['fleet.vehicle'].get_view(self.env.ref('fleet.fleet_vehicle_view_form').id, 'form')['arch']
        for name in ('operational_city_id', 'operational_province_id'):
            self.assertRegex(arch, r'name="%s"[^>]*no_create' % name)

    def test_migration_matches_typed_names_without_guessing(self):
        migration = _migration()
        cities = self.boyolali | self.bekasi_city | self.bekasi_regency
        self.assertEqual(migration._match_city(cities, '  BOYOLALI '), self.boyolali)
        self.assertEqual(migration._match_city(cities, 'Kabupaten Boyolali'), self.boyolali)
        self.assertEqual(migration._match_city(cities, 'kota bekasi'), self.bekasi_city)
        # "Bekasi" alone could be the city or the regency.
        self.assertIsNone(migration._match_city(cities, 'Bekasi'))
        self.assertEqual(migration.PROVINCE_ALIASES[migration._key('Jakarta')], 'dki jakarta')

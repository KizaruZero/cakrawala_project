import importlib.util
from pathlib import Path

from lxml import etree

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRpcOtrVehicleTypes(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={
            **cls.env.context, 'tracking_disable': True,
            'mail_create_nosubscribe': True,
        })
        cls.category_model = cls.env['rpc.kendaraan.kategori']
        cls.type_a, cls.type_b, cls.type_c = cls.env['rpc.parameter'].create([
            {'name': f'OTR Test {code}', 'code': f'otr_test_{code}',
             'parameter_type': 'jenis_kendaraan'}
            for code in ('A', 'B', 'C')
        ])
        cls.parameters = {
            field: cls.env['rpc.parameter'].create({
                'name': 'OTR Test ' + parameter_type,
                'parameter_type': parameter_type,
            }).id
            for field, parameter_type in (
                ('type_of_klien_id', 'type_of_klien'),
                ('jenis_transaksi_id', 'jenis_transaksi'),
                ('tujuan_id', 'tujuan'), ('sumber_id', 'sumber'),
                ('sumber_daya_id', 'sumber_daya'),
                ('pemakaian_id', 'pemakaian'), ('merek_id', 'merek'),
            )
        }
        cls.partner = cls.env['res.partner'].create({'name': 'OTR Test Customer'})
        cls.province = cls.env.ref('x_rental_profit_calculation.prov_dki')
        cls.city = cls.env['rpc.kota'].create({
            'name': 'OTR Test City', 'provinsi_id': cls.province.id,
        })

    def _category(self, **values):
        return self.category_model.create({
            'name': 'OTR Test Category', 'group_otr': 'OTR Test Group',
            'jenis_kendaraan_ids': [Command.set((self.type_a | self.type_b).ids)],
            'otr_from': 0, 'otr_to': 500000000, **values,
        })

    def _document(self, **values):
        return self.env['rpc.document'].create({
            **self.parameters,
            'partner_id': self.partner.id, 'provinsi_id': self.province.id,
            'kota_id': self.city.id, 'jenis_kendaraan_id': self.type_a.id,
            'tahun_mulai_sewa': 2026, 'masa_sewa': 36, 'jumlah_unit': 2,
            'term_of_payment_due': 'addm', 'term_of_payment_hari': 30,
            'sewa_per_bulan_batas_atas': 10000000,
            'sewa_per_bulan_batas_bawah': 9000000,
            'harga_otr': 451100000, **values,
        })

    def _migration(self):
        path = Path(__file__).parent.parent / 'migrations' / '19.0.1.0.115' / 'post-migrate.py'
        spec = importlib.util.spec_from_file_location('rpc_otr_m2m_upgrade', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        return migration

    def test_category_accepts_multiple_types_and_matches_either_not_unrelated(self):
        category = self._category()
        self.assertEqual(category.jenis_kendaraan_ids, self.type_a | self.type_b)
        self.assertFalse(category.jenis_kendaraan_id)
        for vehicle_type in (self.type_a, self.type_b):
            document = self._document(jenis_kendaraan_id=vehicle_type.id)
            self.assertEqual(document.insurance_kategori_id, category)
            self.assertEqual(document.insurance_group_otr, category.group_otr)
        self.assertFalse(self._document(jenis_kendaraan_id=self.type_c.id).insurance_kategori_id)

    def test_rpc_type_and_otr_changes_refresh_category_with_same_range_rules(self):
        low = self._category(otr_to=100000000)
        high = self._category(otr_from=100000000, otr_to=0)
        document = self._document(harga_otr=100000000)
        # Existing inclusive limits and lowest otr_from/id priority are retained.
        self.assertEqual(document.insurance_kategori_id, low)
        document.harga_otr = 100000001
        self.assertEqual(document.insurance_kategori_id, high)
        document.jenis_kendaraan_id = self.type_c
        self.assertFalse(document.insurance_kategori_id)
        document.jenis_kendaraan_id = self.type_b
        self.assertEqual(document.insurance_kategori_id, high)
        for price in (0, -1):
            document.harga_otr = price
            self.assertFalse(document.insurance_kategori_id)

    def test_archived_category_is_not_auto_selected(self):
        self._category(active=False)
        self.assertFalse(self._document().insurance_kategori_id)

    def test_duplicate_matches_select_one_category_without_combining_rates(self):
        first = self._category()
        self._category()
        self.assertEqual(self._document().insurance_kategori_id, first)

    def test_insurance_rate_amount_years_and_manual_override_are_unchanged(self):
        category = self._category()
        self.env['rpc.asuransi.rate'].create({
            'wilayah_id': self.province.wilayah_id.id,
            'kategori_id': category.id, 'wilayah_type': 'crs', 'rate': 0.02,
        })
        for vehicle_type in (self.type_a, self.type_b):
            document = self._document(jenis_kendaraan_id=vehicle_type.id, insurance_type='crs')
            document._generate_insurance_lines()
            self.assertEqual(len(document.insurance_line_ids), 3)
            self.assertEqual(document.insurance_line_ids.mapped('tahun'), [2026, 2027, 2028])
            self.assertEqual(set(document.insurance_line_ids.mapped('rate')), {0.02})
            self.assertEqual(set(document.insurance_line_ids.mapped('amount')), {9022000})
            manual = self._category(name='OTR Manual Category')
            document.insurance_kategori_id = manual
            document.write({'name': 'OTR manual override retained'})
            self.assertEqual(document.insurance_kategori_id, manual)
            document.harga_otr = 451200000
            self.assertEqual(document.insurance_kategori_id, category)

    def test_empty_or_wrong_parameter_type_is_rejected_on_create_and_write(self):
        invalid = self.env['rpc.parameter'].create({
            'name': 'Not a vehicle type', 'parameter_type': 'merek',
        })
        for values in (
            {'jenis_kendaraan_ids': [Command.clear()]},
            {'jenis_kendaraan_ids': [Command.set(invalid.ids)]},
            {'jenis_kendaraan_ids': [Command.set((self.type_a | invalid).ids)]},
        ):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self._category(**values)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.category_model.create({'name': 'Missing type', 'group_otr': 'Missing'})
        category = self._category()
        for command in (Command.clear(), Command.set([]), Command.set(invalid.ids)):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                category.write({'jenis_kendaraan_ids': [command]})
        self.assertEqual(category.jenis_kendaraan_ids, self.type_a | self.type_b)

    def test_legacy_scalar_inputs_still_work_without_restricting_m2m(self):
        category = self.category_model.create({
            'name': 'Legacy OTR', 'group_otr': 'Legacy',
            'jenis_kendaraan_id': self.type_a.id,
        })
        self.assertEqual(category.jenis_kendaraan_ids, self.type_a)
        category.write({'jenis_kendaraan': self.type_b.code})
        self.assertEqual(category.jenis_kendaraan_ids, self.type_b)
        category.write({'jenis_kendaraan_ids': [Command.link(self.type_a.id)]})
        self.assertEqual(category.jenis_kendaraan_ids, self.type_a | self.type_b)
        self.assertFalse(category.jenis_kendaraan_id)
        self.assertFalse(category.jenis_kendaraan)
        category.write({'jenis_kendaraan_ids': [Command.unlink(self.type_b.id)]})
        self.assertEqual(category.jenis_kendaraan_id, self.type_a)
        self.assertEqual(category.jenis_kendaraan, self.type_a.code)
        self.assertEqual(category.copy().jenis_kendaraan_ids, self.type_a)

    def test_views_use_multiple_tags_and_form_can_save_multiple_types(self):
        for name in ('view_rpc_kendaraan_kategori_list', 'view_rpc_kendaraan_kategori_form'):
            arch = etree.fromstring(self.env.ref(f'x_rental_profit_calculation.{name}').arch_db)
            fields = arch.xpath('//field[@name="jenis_kendaraan_ids"]')
            self.assertEqual(len(fields), 1)
            self.assertEqual(fields[0].get('widget'), 'many2many_tags')
            self.assertFalse(arch.xpath('//field[@name="jenis_kendaraan_id"]'))
        with Form(self.category_model, view='x_rental_profit_calculation.view_rpc_kendaraan_kategori_form') as form:
            form.name = 'Multi-type OTR Form'
            form.group_otr = 'Multi-type Form'
            form.jenis_kendaraan_ids.add(self.type_a)
            form.jenis_kendaraan_ids.add(self.type_b)
        self.assertEqual(form.record.jenis_kendaraan_ids, self.type_a | self.type_b)

    def test_seed_data_retains_original_single_vehicle_mapping(self):
        for index, code in enumerate(
            ['non_bus_non_truk'] * 5 + ['truk_pickup', 'bus', 'roda_2'], start=1,
        ):
            category = self.env.ref(f'x_rental_profit_calculation.kategori_{index}')
            self.assertEqual(len(category.jenis_kendaraan_ids), 1)
            self.assertEqual(category.jenis_kendaraan_ids.code, code)

    def test_upgrade_preserves_old_and_archived_types_is_idempotent_and_keeps_rpc(self):
        old = self.category_model.create({
            'name': 'Archived legacy category', 'group_otr': 'Old',
            'active': False, 'jenis_kendaraan_id': self.type_a.id,
        })
        code_only = self._category(name='Code-only legacy category')
        existing = self._category(name='Keep existing multiple types')
        self.env['rpc.asuransi.rate'].create({
            'wilayah_id': self.province.wilayah_id.id,
            'kategori_id': existing.id, 'wilayah_type': 'crs', 'rate': 0.02,
        })
        document = self._document(insurance_kategori_id=existing.id, insurance_type='crs')
        document._generate_insurance_lines()
        document.state = 'approved'
        before = document.read(['insurance_kategori_id', 'state', 'otr_final', 'insurance_line_ids'])
        amounts_before = document.insurance_line_ids.read(['rate', 'amount'])
        self.type_a.active = False
        self.env.flush_all()
        # Simulate a real pre-upgrade database with legacy columns only.
        self.cr.execute(
            'DELETE FROM rpc_kategori_jenis_kendaraan_rel WHERE kategori_id IN %s',
            [tuple((old | code_only).ids)],
        )
        self.cr.execute(
            'UPDATE rpc_kendaraan_kategori SET jenis_kendaraan_id=NULL, jenis_kendaraan=%s WHERE id=%s',
            [self.type_b.code, code_only.id],
        )
        self.env.invalidate_all()
        migration = self._migration()
        for _attempt in range(2):
            migration.migrate(self.cr, '19.0.1.0.114')
            self.assertEqual(old.with_context(active_test=False).jenis_kendaraan_ids, self.type_a)
            self.assertEqual(code_only.jenis_kendaraan_ids, self.type_b)
            self.assertEqual(existing.with_context(active_test=False).jenis_kendaraan_ids, self.type_a | self.type_b)
            self.assertEqual(document.read(['insurance_kategori_id', 'state', 'otr_final', 'insurance_line_ids']), before)
            self.assertEqual(document.insurance_line_ids.read(['rate', 'amount']), amounts_before)

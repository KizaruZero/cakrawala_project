from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestInsuranceFields(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.insurance_type = cls.env['fleet.service.type'].create({
            'name': 'Asuransi Test', 'category': 'contract', 'is_insurance': True,
        })
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'Insurance Brand'})
        model = cls.env['fleet.vehicle.model'].create({'name': 'Insurance Model', 'brand_id': brand.id})
        cls.vehicle = cls.env['fleet.vehicle'].create({
            'model_id': model.id, 'license_plate': 'B 77 INS', 'initial_license_plate': 'B 77 INS',
            'asset_number': 'INS-B77',
        })
        cls.flood, cls.riot = cls.env['fleet.insurance.coverage'].create([{'name': 'Banjir Test'}, {'name': 'Huru-hara Test'}])

    def test_document_holds_amount_type_and_several_coverages(self):
        document = self.env['fleet.vehicle.log.contract'].create({
            'vehicle_id': self.vehicle.id, 'cost_subtype_id': self.insurance_type.id,
            'insured_amount': 350_000_000, 'coverage_type': 'total_loss_only',
            'insurance_coverage_ids': [(6, 0, (self.flood | self.riot).ids)],
        })
        self.assertTrue(document.is_insurance)
        self.assertEqual(document.insured_amount, 350_000_000)
        self.assertEqual(document.currency_id, document.company_id.currency_id)
        self.assertEqual(document.insurance_coverage_ids, self.flood | self.riot)

    def test_insurance_fields_show_only_for_an_insurance_type(self):
        arch = etree.fromstring(self.env['fleet.vehicle.log.contract'].get_view(
            self.env.ref('fleet.fleet_vehicle_log_contract_view_form').id, 'form')['arch'])
        for name in ('insurance_partner_id', 'policy_number', 'insured_amount', 'coverage_type',
                     'insurance_coverage_ids'):
            node = arch.xpath("//field[@name='%s']" % name)[0]
            self.assertEqual(node.get('invisible'), 'not is_insurance', name)
        self.assertIn('no_create', arch.xpath("//field[@name='insurance_coverage_ids']")[0].get('options'))
        self.assertFalse(arch.xpath("//field[@name='insurance_coverage']"))

    def test_only_a_fleet_administrator_manages_the_coverage_master(self):
        user = new_test_user(self.env, 'fleet_insurance_user', groups='fleet.fleet_group_user')
        manager = new_test_user(self.env, 'fleet_insurance_manager', groups='fleet.fleet_group_manager')
        self.assertTrue(self.flood.with_user(user).name)
        with self.assertRaises(AccessError):
            self.env['fleet.insurance.coverage'].with_user(user).create({'name': 'TPL Test'})
        self.assertTrue(self.env['fleet.insurance.coverage'].with_user(manager).create({'name': 'TPL Test'}))

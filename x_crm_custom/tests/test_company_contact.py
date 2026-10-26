import runpy
from pathlib import Path

from lxml import etree

from odoo.exceptions import ValidationError
from odoo.modules.module import get_module_path
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCrmCompanyContact(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={
            **cls.env.context, 'tracking_disable': True,
            'mail_create_nosubscribe': True, 'lang': 'en_US',
        })
        cls.stage = cls.env['crm.stage'].create({'name': 'New Leads', 'sequence': -1000})
        cls.offering = cls.env['crm.stage'].create({'name': 'Offering', 'sequence': 9999})
        cls.leads = cls.env['crm.lead'].with_context(
            default_type='opportunity', default_stage_id=cls.stage.id,
        )
        cls.customer = cls.env['res.partner'].create({
            'name': 'PT ARUTMIN COMPANY TEST', 'is_company': True,
            'street': 'Company address', 'email': 'company@example.test', 'phone': '+628111111111',
        })
        cls.other_customer = cls.env['res.partner'].create({
            'name': 'PT OTHER COMPANY TEST', 'is_company': True,
            'street': 'Other company address', 'email': 'other-company@example.test', 'phone': '+628122222222',
        })
        cls.pic = cls.env['res.partner'].create({
            'name': 'Indri', 'parent_id': cls.customer.id, 'type': 'contact',
            'function': 'Procurement Manager', 'email': 'indri@example.test',
            'phone': '+628177626762', 'street': 'PIC different address',
        })
        cls.second_pic = cls.env['res.partner'].create({
            'name': 'Other PIC', 'parent_id': cls.customer.id,
            'function': 'Director', 'email': 'director@example.test', 'phone': '+628133333333',
        })
        cls.other_pic = cls.env['res.partner'].create({
            'name': 'Other Company PIC', 'parent_id': cls.other_customer.id,
            'function': 'Other Manager', 'email': 'other-pic@example.test', 'phone': '+628144444444',
        })
        cls.parameters = {
            field: cls.env['rpc.parameter'].create({'name': 'CRM Contact Test ' + parameter, 'parameter_type': parameter})
            for field, parameter in (
                ('client_type_id', 'type_of_klien'), ('tujuan_id', 'tujuan'),
                ('jenis_transaksi_id', 'jenis_transaksi'), ('custom_source_id', 'sumber'),
            )
        }
        province = cls.env.ref('x_rental_profit_calculation.prov_dki')
        city = cls.env['rpc.kota'].create({'name': 'CRM Company Test City', 'provinsi_id': province.id})
        product = cls.env['product.product'].create({'name': 'CRM Company Test Vehicle', 'is_vehicle': True})
        cls.rpc_values = {
            name: cls.env['rpc.parameter'].create({'name': 'RPC Contact Test ' + parameter, 'parameter_type': parameter}).id
            for name, parameter in (
                ('sumber_daya_id', 'sumber_daya'), ('jenis_kendaraan_id', 'jenis_kendaraan'),
                ('pemakaian', 'pemakaian'),
            )
        }
        cls.rpc_values.update({
            'state_id': province.id, 'city_id': city.id,
            'merek_id': product.product_tmpl_id.id, 'tipe_kendaraan_id': product.id,
            'masa_sewa': 36, 'quantity': 1,
        })

    def _lead(self, **values):
        return self.leads.create({
            'name': 'Company contact opportunity', 'partner_id': self.customer.id,
            'contact_partner_id': self.pic.id,
            **{name: parameter.id for name, parameter in self.parameters.items()},
            **values,
        })

    def _assert_pic(self, lead, company=None, pic=None):
        company = company or self.customer
        pic = pic or self.pic
        self.assertEqual(lead.partner_id, company)
        self.assertEqual(lead.contact_partner_id, pic)
        self.assertEqual(lead.contact_name, pic.name)
        self.assertEqual(lead.job_position, pic.function)
        self.assertEqual(lead.function, pic.function)
        self.assertEqual(lead.email_from, pic.email)
        self.assertEqual(lead.phone_sanitized, pic.phone_sanitized)

    def _assert_master_contacts_unchanged(self, before):
        partners = self.customer | self.pic
        self.assertEqual(partners.read(['name', 'function', 'email', 'phone', 'parent_id']), before)

    def _run_migration(self):
        path = Path(get_module_path('x_crm_custom')) / 'migrations/19.0.1.0.9/post-migrate.py'
        runpy.run_path(str(path))['migrate'](self.env.cr, '19.0.1.0.8')
        self.env.invalidate_all()

    def _make_legacy(self, lead, **values):
        lead.flush_recordset()
        self.env.cr.execute('''
            UPDATE crm_lead SET partner_id = %s, contact_partner_id = NULL,
                job_position = %s, function = %s, name = %s WHERE id = %s
        ''', [self.pic.id, values.get('job_position'), values.get('function'),
              values.get('name', 'Legacy Mixed Name'), lead.id])
        lead.invalidate_recordset()

    def test_quick_create_selects_company_then_its_pic_and_keeps_details_after_save(self):
        before = (self.customer | self.pic).read(['name', 'function', 'email', 'phone', 'parent_id'])
        with Form(self.leads, view='crm.quick_create_opportunity_form') as form:
            self.assertTrue(form._get_modifier('contact_partner_id', 'readonly'))
            form.partner_id = self.customer
            self.assertEqual(form.name, "PT ARUTMIN COMPANY TEST'S OPPORTUNITY")
            self.assertFalse(form._get_modifier('contact_partner_id', 'readonly'))
            form.contact_partner_id = self.pic
            self.assertEqual(form.partner_id, self.customer)
            self.assertEqual(form.contact_name, 'Indri')
            self.assertEqual(form.job_position, 'Procurement Manager')
            self.assertEqual(form.email_from, self.pic.email)
        lead = form.record
        self._assert_pic(lead)
        self.assertEqual(lead.street, self.customer.street)
        lead.invalidate_recordset()
        self._assert_pic(lead)
        self._assert_master_contacts_unchanged(before)

    def test_api_create_maps_job_position_and_retains_company_address(self):
        values = {'name': 'New API opportunity', 'partner_id': self.customer.id, 'contact_partner_id': self.pic.id}
        lead = self.leads.create(values)
        self._assert_pic(lead)
        self.assertEqual(lead.street, self.customer.street)
        self.assertNotIn('job_position', values)

    def test_legacy_api_contact_as_customer_is_normalized(self):
        lead = self.leads.create({'name': 'Legacy API quick create', 'partner_id': self.pic.id})
        self._assert_pic(lead)
        lead.write({'partner_id': self.other_pic.id})
        self._assert_pic(lead, self.other_customer, self.other_pic)

    def test_context_defaults_and_pic_only_api_resolve_company(self):
        lead = self.leads.with_context(default_partner_id=self.pic.id).create({'name': 'Context PIC'})
        self._assert_pic(lead)
        lead = self.leads.create({'name': 'PIC only', 'contact_partner_id': self.pic.id})
        self._assert_pic(lead)

    def test_selecting_another_pic_updates_snapshots_without_changing_company(self):
        lead = self._lead()
        lead.contact_partner_id = self.second_pic
        self._assert_pic(lead, self.customer, self.second_pic)

    def test_switching_company_clears_old_pic_and_job(self):
        lead = self._lead()
        lead.partner_id = self.other_customer
        self.assertEqual(lead.partner_id, self.other_customer)
        self.assertFalse(lead.contact_partner_id)
        self.assertFalse(lead.contact_name)
        self.assertFalse(lead.job_position)
        self.assertEqual(lead.email_from, self.other_customer.email)
        self.assertEqual(lead.street, self.other_customer.street)
        lead.contact_partner_id = self.other_pic
        self._assert_pic(lead, self.other_customer, self.other_pic)

    def test_clearing_pic_clears_stale_job_but_keeps_company(self):
        lead = self._lead()
        lead.contact_partner_id = False
        self.assertEqual(lead.partner_id, self.customer)
        self.assertFalse(lead.contact_name)
        self.assertFalse(lead.job_position)
        self.assertFalse(lead.function)
        self.assertEqual(lead.email_from, self.customer.email)

    def test_wrong_company_company_as_pic_and_address_contacts_are_rejected(self):
        address = self.env['res.partner'].create({
            'name': 'Delivery address', 'parent_id': self.customer.id, 'type': 'delivery',
        })
        lead = self._lead()
        for pic in (self.other_pic, self.customer, address):
            with self.subTest(pic=pic.name):
                with self.assertRaisesRegex(ValidationError, 'contact person'):
                    lead.write({'contact_partner_id': pic.id})
                self._assert_pic(lead)

    def test_manual_lead_overrides_do_not_write_to_company_or_pic(self):
        before = (self.customer | self.pic).read(['name', 'function', 'email', 'phone', 'parent_id'])
        lead = self._lead()
        lead.write({'job_position': 'Manual job', 'email_from': 'manual@example.test', 'phone': '+628199999999'})
        lead.description = 'Unrelated save'
        lead.write({'partner_id': self.customer.id, 'contact_partner_id': self.pic.id})
        self.assertEqual(lead.job_position, 'Manual job')
        self.assertEqual(lead.email_from, 'manual@example.test')
        self.assertEqual(lead.phone_sanitized, '+628199999999')
        self.assertFalse(lead.partner_email_update)
        self.assertFalse(lead.partner_phone_update)
        self._assert_master_contacts_unchanged(before)

    def test_explicit_create_overrides_are_preserved(self):
        lead = self._lead(job_position='Manual role', email_from='special@example.test', phone='+628155555555')
        self.assertEqual(lead.job_position, 'Manual role')
        self.assertEqual(lead.email_from, 'special@example.test')
        self.assertEqual(lead.phone_sanitized, '+628155555555')

    def test_batch_create_and_write_do_not_mix_companies_or_contact_details(self):
        leads = self.leads.create([
            {'name': 'One', 'partner_id': self.pic.id},
            {'name': 'Two', 'partner_id': self.other_pic.id},
        ])
        self._assert_pic(leads[0])
        self._assert_pic(leads[1], self.other_customer, self.other_pic)
        leads.write({'contact_partner_id': False})
        self.assertFalse(leads.contact_partner_id)
        self.assertEqual(leads.mapped('partner_id'), self.customer | self.other_customer)
        self.assertEqual(leads[0].email_from, self.customer.email)
        self.assertEqual(leads[1].email_from, self.other_customer.email)

    def test_full_form_uses_same_company_pic_job_mapping(self):
        lead = self._lead()
        with Form(lead, view='crm.crm_lead_view_form') as form:
            for name, parameter in self.parameters.items():
                setattr(form, name, parameter)
            form.contact_partner_id = self.second_pic
            self.assertEqual(form.job_position, self.second_pic.function)
            self.assertEqual(form.partner_id, self.customer)
        self._assert_pic(lead, self.customer, self.second_pic)

    def test_company_change_in_quick_form_does_not_keep_stale_contact(self):
        with Form(self.leads, view='crm.quick_create_opportunity_form') as form:
            form.partner_id = self.customer
            form.contact_partner_id = self.pic
            form.partner_id = self.other_customer
            self.assertFalse(form.contact_partner_id)
            self.assertFalse(form.job_position)
            form.contact_partner_id = self.other_pic
        self._assert_pic(form.record, self.other_customer, self.other_pic)

    def test_missing_job_does_not_copy_previous_pic_job(self):
        empty_pic = self.env['res.partner'].create({'name': 'PIC Without Job', 'parent_id': self.customer.id})
        lead = self._lead()
        lead.contact_partner_id = empty_pic
        self.assertFalse(lead.job_position)
        self.assertFalse(lead.function)

    def test_new_customer_offering_creates_company_and_child_pic(self):
        lead = self.leads.create({
            'name': 'New customer offering', 'stage_id': self.offering.id,
            'is_new_customer': True, 'new_customer_name': 'PT New Company',
            'new_customer_address': 'New Company Address', 'contact_name': 'New PIC',
            'job_position': 'New Manager', 'email_from': 'new-pic@example.test', 'phone': '+628166666666',
        })
        self.assertTrue(lead.partner_id.is_company)
        self.assertEqual(lead.partner_id.name, 'PT New Company')
        self.assertEqual(lead.contact_partner_id.parent_id, lead.partner_id)
        self.assertEqual(lead.contact_partner_id.function, 'New Manager')
        self.assertFalse(lead.partner_id.email)
        self.assertEqual(lead.job_position, 'New Manager')
        self.assertFalse(lead.is_new_customer)

    def test_stage_change_keeps_new_customer_flow_and_separates_each_company(self):
        values = {name: parameter.id for name, parameter in self.parameters.items()}
        leads = self.leads.create([{
            'name': 'New ' + name, 'is_new_customer': True,
            'new_customer_name': name, 'contact_name': name + ' PIC',
            'job_position': 'Manager', 'email_from': name.lower() + '@example.test',
            'phone': '+628188888888', **values,
        } for name in ('Alpha', 'Bravo')])
        leads.write({'stage_id': self.offering.id})
        self.assertEqual(len(leads.partner_id), 2)
        self.assertEqual(leads.mapped('partner_id.name'), ['Alpha', 'Bravo'])
        for lead in leads:
            self.assertEqual(lead.contact_partner_id.parent_id, lead.partner_id)
            self.assertEqual(lead.contact_partner_id.name, lead.contact_name)

    def test_new_rpc_uses_company_not_contact_person(self):
        lead = self._lead(**self.rpc_values)
        action = lead.action_create_rpc()
        rpc = self.env['rpc.document'].browse(action['res_id'])
        self.assertEqual(rpc.partner_id, self.customer)
        self.assertNotEqual(rpc.partner_id, self.pic)

    def test_migration_repairs_archived_legacy_link_and_fills_empty_job(self):
        lead = self._lead(**self.rpc_values)
        action = lead.action_create_rpc()
        rpc = self.env['rpc.document'].browse(action['res_id'])
        rpc.partner_id = self.pic
        self._make_legacy(lead)
        lead.active = False
        self.pic.active = False
        before = (self.customer | self.pic).read(['name', 'function', 'email', 'phone', 'parent_id'])
        self._run_migration()
        self._assert_pic(lead)
        self.assertEqual(lead.name, 'Legacy Mixed Name')
        self.assertEqual(lead.stage_id, self.stage)
        self.assertFalse(lead.active)
        self.assertEqual(rpc.partner_id, self.pic)
        self._assert_master_contacts_unchanged(before)
        self._run_migration()
        self._assert_pic(lead)

    def test_migration_preserves_manual_details_and_does_not_guess_individual_company(self):
        lead = self._lead(job_position='Manual Job', email_from='manual@example.test')
        self._make_legacy(lead, job_position='Manual Job', function='Manual Function')
        standalone = self.env['res.partner'].create({'name': 'Standalone Individual'})
        individual_lead = self.leads.create({'name': 'Individual', 'partner_id': standalone.id})
        self._run_migration()
        self.assertEqual(lead.partner_id, self.customer)
        self.assertEqual(lead.contact_partner_id, self.pic)
        self.assertEqual(lead.job_position, 'Manual Job')
        self.assertEqual(lead.email_from, 'manual@example.test')
        self.assertEqual(individual_lead.partner_id, standalone)
        self.assertFalse(individual_lead.contact_partner_id)

    def test_views_filter_company_and_pic_by_company_and_preserve_uppercase(self):
        for view_id in ('crm.quick_create_opportunity_form', 'crm.crm_lead_view_form'):
            architecture = etree.fromstring(self.leads.get_view(
                view_id=self.env.ref(view_id).id, view_type='form',
            )['arch'])
            company = architecture.xpath('//field[@name="partner_id"][@domain="[(\'is_company\', \'=\', True)]"]')
            self.assertTrue(company)
            self.assertTrue(architecture.xpath('//field[@name="contact_partner_id"]'))
            self.assertTrue(architecture.xpath('//field[@name="name"][contains(@class,"o_crm_opportunity_uppercase")]'))
        domain = self.leads._fields['contact_partner_id'].domain
        self.assertIn("('commercial_partner_id', '=', partner_id)", domain)
        self.assertIn("('type', '=', 'contact')", domain)

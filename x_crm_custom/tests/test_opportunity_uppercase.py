from lxml import etree

from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOpportunityUppercase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={
            **cls.env.context,
            'tracking_disable': True,
            'mail_create_nosubscribe': True,
            'lang': 'en_US',
        })
        cls.stage = cls.env['crm.stage'].create({'name': 'New Leads', 'sequence': -1000})
        cls.leads = cls.env['crm.lead'].with_context(
            default_type='opportunity', default_stage_id=cls.stage.id,
        )

    def _lead(self, **values):
        return self.leads.create({'name': 'Sewa kendaraan 2026', **values})

    def test_create_normalizes_only_opportunity_name(self):
        values = {
            'name': 'Sewa kendaraan - PT Contoh 2026',
            'email_from': 'Sales.Contact@example.test',
            'phone': '+6281234567890',
            'contact_name': 'Dwi Lestari',
            'partner_name': 'PT Pelanggan Baru',
        }
        lead = self.leads.create(values)
        self.assertEqual(lead.name, values['name'].upper())
        for field_name in ('email_from', 'phone', 'contact_name', 'partner_name'):
            self.assertEqual(lead[field_name], values[field_name])
        self.assertEqual(values['name'], 'Sewa kendaraan - PT Contoh 2026')

    def test_batch_create(self):
        leads = self.leads.create([
            {'name': 'Sewa mobil pertama'}, {'name': 'Sewa mobil kedua'},
        ])
        self.assertEqual(leads.mapped('name'), ['SEWA MOBIL PERTAMA', 'SEWA MOBIL KEDUA'])

    def test_context_default_name(self):
        lead = self.leads.with_context(default_name='Sewa dari context').create({})
        self.assertEqual(lead.name, 'SEWA DARI CONTEXT')

    def test_partner_generated_default_name(self):
        partner = self.env['res.partner'].create({'name': 'PT Contoh Pelanggan'})
        # CRM generates this default in the form before saving the required
        # name; its stored computed field is not precomputed on bare create.
        with Form(self.leads, view='crm.quick_create_opportunity_form') as form:
            form.partner_id = partner
            self.assertEqual(form.name, "PT CONTOH PELANGGAN'S OPPORTUNITY")
        self.assertEqual(form.record.name, "PT CONTOH PELANGGAN'S OPPORTUNITY")
        self.assertEqual(partner.name, 'PT Contoh Pelanggan')

    def test_many2one_name_create(self):
        lead_id, _display_name = self.leads.name_create('Sewa melalui quick create')
        self.assertEqual(self.leads.browse(lead_id).name, 'SEWA MELALUI QUICK CREATE')

    def test_lead_type_also_uses_uppercase(self):
        self.assertEqual(self._lead(type='lead').name, 'SEWA KENDARAAN 2026')

    def test_rename_and_multi_record_write(self):
        leads = self._lead() | self._lead(name='Unit kedua')
        values = {'name': 'Perpanjangan sewa 36 bulan'}
        leads.write(values)
        self.assertEqual(leads.mapped('name'), ['PERPANJANGAN SEWA 36 BULAN'] * 2)
        self.assertEqual(values['name'], 'Perpanjangan sewa 36 bulan')

    def test_onchange_before_save(self):
        lead = self.leads.new({'name': 'Penawaran mobil baru'})
        lead._onchange_uppercase_opportunity_name()
        self.assertEqual(lead.name, 'PENAWARAN MOBIL BARU')
        empty_lead = self.leads.new({'name': False})
        empty_lead._onchange_uppercase_opportunity_name()
        self.assertFalse(empty_lead.name)

    def test_quick_create_form_uses_onchange_and_saves_uppercase(self):
        with Form(self.leads, view='crm.quick_create_opportunity_form') as form:
            form.name = 'Sewa unit dari pipeline'
            self.assertEqual(form.name, 'SEWA UNIT DARI PIPELINE')
            form.email_from = 'Pipeline.Contact@example.test'
            form.phone = '+6281234567890'
        self.assertEqual(form.record.name, 'SEWA UNIT DARI PIPELINE')
        self.assertEqual(form.record.email_from, 'Pipeline.Contact@example.test')
        # Keep CRM's native international phone formatting intact.
        self.assertEqual(form.record.phone_sanitized, '+6281234567890')

    def test_legacy_names_are_not_rewritten_on_unrelated_updates(self):
        lead = self._lead()
        self.env.cr.execute('UPDATE crm_lead SET name = %s WHERE id = %s', ['Legacy mixed Name', lead.id])
        lead.invalidate_recordset(['name'])
        lead.write({'email_from': 'Legacy.Contact@example.test'})
        self.assertEqual(lead.name, 'Legacy mixed Name')
        partner = self.env['res.partner'].create({'name': 'New Customer'})
        lead.partner_id = partner
        self.assertEqual(lead.name, 'Legacy mixed Name')

    def test_copy_normalizes_new_name(self):
        self.assertEqual(self._lead().copy({'name': 'Sewa unit tambahan'}).name, 'SEWA UNIT TAMBAHAN')

    def test_numbers_punctuation_and_accents_are_preserved(self):
        name = 'Sewa café / unit-02 (36 bulan)'
        self.assertEqual(self._lead(name=name).name, 'SEWA CAFÉ / UNIT-02 (36 BULAN)')

    def test_existing_new_customer_creation_still_preserves_customer_name(self):
        offering = self.env['crm.stage'].create({'name': 'Offering', 'sequence': 9999})
        lead = self._lead(
            stage_id=offering.id, is_new_customer=True,
            new_customer_name='PT Pelanggan Baru', new_customer_address='Jl. Contoh No. 10',
        )
        self.assertEqual(lead.name, 'SEWA KENDARAAN 2026')
        self.assertEqual(lead.partner_id.name, 'PT Pelanggan Baru')
        self.assertFalse(lead.is_new_customer)

    def test_uppercase_input_style_is_limited_to_name_fields(self):
        for view_id in ('crm.quick_create_opportunity_form', 'crm.crm_lead_view_form'):
            with self.subTest(view=view_id):
                result = self.leads.get_view(view_id=self.env.ref(view_id).id, view_type='form')
                root = etree.fromstring(result['arch'])
                styled_fields = root.xpath('//field[contains(@class, "o_crm_opportunity_uppercase")]')
                self.assertTrue(styled_fields)
                self.assertEqual({node.get('name') for node in styled_fields}, {'name'})

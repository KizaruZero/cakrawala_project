from lxml import etree

from odoo.tests import Form, TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


@tagged('post_install', '-at_install')
class TestCrmTotalForecast(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={
            **cls.env.context, 'tracking_disable': True,
            'mail_create_nosubscribe': True,
        })
        cls.env.company.currency_id = cls.env.ref('base.IDR')

    def _lead(self, **values):
        return self.env['crm.lead'].create({
            'name': 'CRM Monetary Forecast Test',
            'company_id': self.env.company.id,
            'sewa_per_bulan': 4300000, 'masa_sewa': 36,
            **values,
        })

    def test_field_and_view_use_native_monetary_with_company_currency(self):
        field = self.env['crm.lead']._fields['total_forecast']
        self.assertEqual(field.type, 'monetary')
        self.assertEqual(field.currency_field, 'company_currency')
        self.assertEqual(field.compute, '_compute_total_forecast')
        self.assertTrue(field.store)
        view = self.env.ref('x_crm_custom.crm_lead_view_form_custom')
        arch = etree.fromstring(view.arch_db)
        node = arch.xpath('//field[@name="total_forecast"]')[0]
        self.assertEqual(node.get('widget'), 'monetary')
        self.assertEqual(node.get('readonly'), '1')
        self.assertEqual(safe_eval(node.get('options'))['currency_field'], 'company_currency')
        self.assertTrue(arch.xpath('//field[@name="company_currency"]'))

    def test_formula_stays_rent_times_months_not_quantity(self):
        lead = self._lead(quantity=12)
        self.assertEqual(lead.total_forecast, 154800000)
        lead.quantity = 1
        self.assertEqual(lead.total_forecast, 154800000)
        lead.sewa_per_bulan = 5000000
        self.assertEqual(lead.total_forecast, 180000000)
        lead.masa_sewa = 48
        self.assertEqual(lead.total_forecast, 240000000)
        lead.masa_sewa = 0
        self.assertEqual(lead.total_forecast, 0)

    def test_currency_follows_lead_company_and_uses_active_company_fallback(self):
        lead = self._lead()
        self.assertEqual(lead.company_currency, self.env.ref('base.IDR'))
        other_company = self.env['res.company'].create({
            'name': 'Forecast EUR Test Company', 'company_code': 'FCT',
            'currency_id': self.env.ref('base.EUR').id,
        })
        lead.company_id = other_company
        self.assertEqual(lead.company_currency, other_company.currency_id)
        self.assertEqual(lead.total_forecast, 154800000)
        lead.company_id = False
        self.assertEqual(lead.company_currency, self.env.company.currency_id)

    def test_value_is_stored_and_uses_native_currency_precision(self):
        lead = self._lead(sewa_per_bulan=4300000.125)
        expected = lead.company_currency.round(lead.sewa_per_bulan * lead.masa_sewa)
        self.assertEqual(lead.total_forecast, expected)
        lead.flush_recordset(['total_forecast'])
        lead.invalidate_recordset(['total_forecast'])
        self.assertEqual(lead.total_forecast, expected)

    def test_form_onchange_keeps_forecast_readonly_and_computes_it(self):
        view = self.env['ir.ui.view'].create({
            'name': 'CRM monetary forecast onchange test', 'model': 'crm.lead',
            'arch': '''<form>
                <field name="name"/>
                <field name="company_currency" invisible="1"/>
                <field name="sewa_per_bulan"/>
                <field name="masa_sewa"/>
                <field name="total_forecast" widget="monetary" readonly="1"/>
            </form>''',
        })
        with Form(self.env['crm.lead'], view=view) as form:
            form.name = 'Monetary Forecast Form'
            form.sewa_per_bulan = 4300000
            form.masa_sewa = 36
            self.assertTrue(form._get_modifier('total_forecast', 'readonly'))
            self.assertEqual(form.total_forecast, 154800000)
        self.assertEqual(form.record.total_forecast, 154800000)

    def test_rent_and_otr_are_monetary_and_keep_existing_stage_requirements(self):
        arch = etree.fromstring(self.env.ref('x_crm_custom.crm_lead_view_form_custom').arch_db)
        for name in ('sewa_per_bulan', 'harga_otr'):
            with self.subTest(field=name):
                field = self.env['crm.lead']._fields[name]
                self.assertEqual(field.type, 'monetary')
                self.assertEqual(field.currency_field, 'company_currency')
                self.assertFalse(field.readonly)
                node = arch.xpath(f'//field[@name="{name}"]')[0]
                self.assertEqual(node.get('widget'), 'monetary')
                self.assertEqual(safe_eval(node.get('options'))['currency_field'], 'company_currency')
                self.assertEqual(node.get('required'), "stage_name in ['Offering', 'Negotiation', 'Deal', 'Delivery']")
                self.assertEqual(node.get('readonly'), "stage_name != 'Offering'")
                self.assertEqual(node.get('force_save'), '1')

    def test_rent_and_otr_keep_native_currency_precision_and_persisted_values(self):
        lead = self._lead(sewa_per_bulan=4300000.125, harga_otr=451100000.125)
        currency = lead.company_currency
        expected_rent = currency.round(4300000.125)
        expected_otr = currency.round(451100000.125)
        self.assertEqual(lead.sewa_per_bulan, expected_rent)
        self.assertEqual(lead.harga_otr, expected_otr)
        self.assertEqual(lead.total_forecast, currency.round(expected_rent * 36))
        lead.flush_recordset()
        lead.invalidate_recordset()
        self.assertEqual(lead.sewa_per_bulan, expected_rent)
        self.assertEqual(lead.harga_otr, expected_otr)
        lead.write({'sewa_per_bulan': 0, 'harga_otr': 0})
        self.assertEqual(lead.total_forecast, 0)
        self.assertEqual(lead.harga_otr, 0)

    def test_price_form_fields_stay_editable_and_update_forecast(self):
        view = self.env['ir.ui.view'].create({
            'name': 'CRM monetary price inputs test', 'model': 'crm.lead',
            'arch': '''<form>
                <field name="name"/>
                <field name="company_currency" invisible="1"/>
                <field name="sewa_per_bulan" widget="monetary"/>
                <field name="harga_otr" widget="monetary"/>
                <field name="masa_sewa"/>
                <field name="total_forecast" widget="monetary" readonly="1"/>
            </form>''',
        })
        with Form(self.env['crm.lead'], view=view) as form:
            form.name = 'CRM Monetary Inputs'
            form.sewa_per_bulan = 4300000
            form.harga_otr = 451100000
            form.masa_sewa = 36
            self.assertFalse(form._get_modifier('sewa_per_bulan', 'readonly'))
            self.assertFalse(form._get_modifier('harga_otr', 'readonly'))
            self.assertEqual(form.total_forecast, 154800000)
        self.assertEqual(form.record.harga_otr, 451100000)

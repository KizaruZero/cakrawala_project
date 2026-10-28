from datetime import date, datetime

from lxml import etree

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestRentalCustomerBillingDefaults(RentalBillingEngineInvoiceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner.write({
            'is_company': True,
            'rental_default_top_billing': 'dibelakang',
            'rental_default_weekend_rule_adjustment': 'next_working_day',
            'rental_default_billing_rule': 'prorate',
        })
        cls.other_partner = cls.env['res.partner'].create({
            'name': 'Customer With Different Rental Defaults',
            'rental_default_top_billing': 'didepan',
            'rental_default_weekend_rule_adjustment': 'previous_working_day',
            'rental_default_billing_rule': 'full_charge',
        })
        cls.empty_partner = cls.env['res.partner'].create({'name': 'Customer Without Rental Defaults'})
        cls.setting_names = ['top_billing', 'weekend_rule_adjustment', 'billing_rule']

    def _values(self, **overrides):
        return {
            'partner_id': self.partner.id, 'is_rental_order': True,
            'rental_type_id': self.rental_type.id, 'state': 'draft',
            'attention_up': 'Customer Billing Defaults Test PIC',
            'location_id': self.location.id, 'invoice_print_lead_time': 0,
            'pricelist_id': self.pricelist.id,
            'rental_start_date': datetime(2026, 1, 14, 5),
            'rental_return_date': datetime(2026, 2, 14, 5),
            'actual_rental_start_date': datetime(2026, 1, 14, 5),
            'masa_sewa_bulan': 1, 'grouping_invoice': 'all_units',
            'invoicing_cycle_period': 'monthly', 'invoicing_date_monthly': '7',
            'journal_id': self.journal.id, 'payment_term_id': self.payment_term.id,
            'order_line': [Command.create(self._line_values(date(2026, 1, 14)))],
            **overrides,
        }

    def _settings(self, order):
        return {name: order[name] for name in self.setting_names}

    def _complete_required_form_header(self, form):
        form.attention_up = 'Customer Billing Defaults Test PIC'
        form.payment_term_id = self.payment_term
        form.rental_type_id = self.rental_type
        form.location_id = self.location
        form.rental_start_date = datetime(2026, 1, 14, 5)
        form.rental_return_date = datetime(2026, 2, 14, 5)
        form.invoicing_cycle_period = 'monthly'
        form.invoicing_date_monthly = '7'
        form.grouping_invoice = 'all_units'

    def test_partner_and_order_selections_match_without_live_related_fields(self):
        mapping = {
            'top_billing': 'rental_default_top_billing',
            'weekend_rule_adjustment': 'rental_default_weekend_rule_adjustment',
            'billing_rule': 'rental_default_billing_rule',
        }
        for order_field, partner_field in mapping.items():
            with self.subTest(field=order_field):
                self.assertEqual(
                    self.order_model._fields[order_field]._description_selection(self.env),
                    self.partner._fields[partner_field]._description_selection(self.env),
                )
                self.assertFalse(self.order_model._fields[order_field].related)
                self.assertFalse(self.order_model._fields[order_field].compute)
                self.assertFalse(self.partner._fields[partner_field].required)
        root = etree.fromstring(self.env.ref('x_sale_purchase_custom.view_partner_form_rental_billing_defaults').arch_db.encode())
        self.assertEqual(len(root.xpath('//group[@name="rental_order_defaults"]/field')), 3)

    def test_create_copies_configured_customer_defaults(self):
        order = self.order_model.create(self._values())
        self.assertEqual(self._settings(order), self.partner._rental_order_billing_defaults())
        self.assertFalse(order.billing_engine_line_ids)

    def test_explicit_order_overrides_and_intentional_blanks_are_preserved(self):
        values = {
            'top_billing': 'didepan', 'weekend_rule_adjustment': 'keep_original', 'billing_rule': 'full_charge',
        }
        order = self.order_model.create(self._values(**values))
        self.assertEqual(self._settings(order), values)
        empty = self.order_model.create(self._values(top_billing=False, billing_rule=False))
        self.assertFalse(empty.top_billing)
        self.assertFalse(empty.billing_rule)
        self.assertEqual(empty.weekend_rule_adjustment, 'next_working_day')

    def test_missing_customer_settings_keep_existing_native_defaults(self):
        order = self.order_model.create(self._values(partner_id=self.empty_partner.id))
        self.assertFalse(order.top_billing)
        self.assertFalse(order.billing_rule)
        self.assertEqual(order.weekend_rule_adjustment, 'keep_original')

    def test_batch_create_resolves_each_customer_separately(self):
        orders = self.order_model.create([
            self._values(), self._values(partner_id=self.other_partner.id),
            self._values(partner_id=self.empty_partner.id),
        ])
        self.assertEqual(self._settings(orders[0]), self.partner._rental_order_billing_defaults())
        self.assertEqual(self._settings(orders[1]), self.other_partner._rental_order_billing_defaults())
        self.assertEqual(self._settings(orders[2]), {
            'top_billing': False, 'weekend_rule_adjustment': 'keep_original', 'billing_rule': False,
        })

    def test_context_partner_and_rental_flag_work_without_explicit_create_values(self):
        values = self._values()
        values.pop('is_rental_order')
        values.pop('partner_id')
        for context in (
            {'default_is_rental_order': True, 'default_partner_id': self.partner.id},
            {'in_rental_app': 1, 'default_partner_id': self.partner.id},
        ):
            with self.subTest(context=context):
                order = self.order_model.with_context(**context).create(dict(values))
                self.assertTrue(order.is_rental_order)
                self.assertEqual(self._settings(order), self.partner._rental_order_billing_defaults())

    def test_default_get_only_returns_requested_customer_defaults(self):
        model = self.order_model.with_context(in_rental_app=1, default_partner_id=self.partner.id)
        defaults = model.default_get(['top_billing'])
        self.assertEqual(defaults, {'top_billing': 'dibelakang'})
        defaults = model.default_get(self.setting_names)
        self.assertEqual(defaults, self.partner._rental_order_billing_defaults())

    def test_explicit_context_defaults_override_customer_defaults(self):
        model = self.order_model.with_context(
            default_is_rental_order=True, default_partner_id=self.partner.id,
            default_top_billing='didepan', default_weekend_rule_adjustment='keep_original',
            default_billing_rule=False,
        )
        expected = {'top_billing': 'didepan', 'weekend_rule_adjustment': 'keep_original', 'billing_rule': False}
        self.assertEqual(model.default_get(self.setting_names), expected)
        order = model.create(self._values())
        self.assertEqual(self._settings(order), expected)

    def test_form_customer_selection_and_manual_changes_survive_save_and_reopen(self):
        model = self.order_model.with_context(in_rental_app=1, default_is_rental_order=True)
        with Form(model, view='sale_renting.rental_order_primary_form_view') as form:
            form.partner_id = self.partner
            form.rental_type_id = self.rental_type
            self.assertEqual(form.top_billing, 'dibelakang')
            self.assertEqual(form.weekend_rule_adjustment, 'next_working_day')
            self.assertEqual(form.billing_rule, 'prorate')
            form.top_billing = 'didepan'
            form.weekend_rule_adjustment = 'keep_original'
            form.billing_rule = 'full_charge'
            self._complete_required_form_header(form)
        order = form.record
        expected = {'top_billing': 'didepan', 'weekend_rule_adjustment': 'keep_original', 'billing_rule': 'full_charge'}
        self.assertEqual(self._settings(order), expected)
        with Form(order, view='sale_renting.rental_order_primary_form_view') as reopened:
            reopened.attention_up = 'Manual billing settings must remain unchanged'
        self.assertEqual(self._settings(order), expected)

    def test_form_changing_customer_reloads_defaults_and_clears_stale_terms(self):
        with Form(self.order_model.with_context(in_rental_app=1),
                  view='sale_renting.rental_order_primary_form_view') as form:
            form.partner_id = self.partner
            self.assertEqual(form.top_billing, 'dibelakang')
            form.partner_id = self.other_partner
            self.assertEqual(form.top_billing, 'didepan')
            self.assertEqual(form.weekend_rule_adjustment, 'previous_working_day')
            self.assertEqual(form.billing_rule, 'full_charge')
            form.partner_id = self.empty_partner
            self.assertFalse(form.top_billing)
            self.assertFalse(form.billing_rule)
            self.assertEqual(form.weekend_rule_adjustment, 'keep_original')
            # The unconfigured customer leaves required choices to the user.
            form.top_billing = 'didepan'
            form.billing_rule = 'full_charge'
            self._complete_required_form_header(form)

    def test_child_contact_overrides_company_per_field(self):
        child = self.env['res.partner'].create({
            'name': 'Rental Contact Under Company', 'parent_id': self.partner.id,
            'rental_default_weekend_rule_adjustment': 'keep_original',
        })
        order = self.order_model.create(self._values(partner_id=child.id))
        self.assertEqual(self._settings(order), {
            'top_billing': 'dibelakang', 'weekend_rule_adjustment': 'keep_original', 'billing_rule': 'prorate',
        })
        self.assertFalse(child.rental_default_top_billing)
        self.partner.rental_default_top_billing = 'didepan'
        self.assertFalse(child.rental_default_top_billing)
        fresh = self.order_model.create(self._values(partner_id=child.id))
        self.assertEqual(fresh.top_billing, 'didepan')
        self.assertEqual(order.top_billing, 'dibelakang')

    def test_customer_update_does_not_rewrite_old_orders_or_engine(self):
        quotation = self.order_model.create(self._values())
        confirmed = self.order_model.create(self._values(state='sale'))
        before_quote = self._settings(quotation)
        before_sale = self._settings(confirmed)
        rows = confirmed.billing_engine_line_ids
        self.assertTrue(rows)
        before_engine = rows.read()
        self.partner.write({
            'rental_default_top_billing': 'didepan',
            'rental_default_weekend_rule_adjustment': 'previous_working_day',
            'rental_default_billing_rule': 'full_charge',
        })
        self.env.flush_all()
        (quotation | confirmed).invalidate_recordset(self.setting_names)
        self.assertEqual(self._settings(quotation), before_quote)
        self.assertEqual(self._settings(confirmed), before_sale)
        self.assertEqual(rows.read(), before_engine)
        self.assertFalse(confirmed.billing_settings_changed)
        self.assertFalse(confirmed.billing_engine_regenerated)
        fresh = self.order_model.create(self._values())
        self.assertEqual(self._settings(fresh), self.partner._rental_order_billing_defaults())

    def test_manual_order_values_drive_billing_engine_not_customer_defaults(self):
        order = self.order_model.create(self._values())
        order.write({
            'top_billing': 'dibelakang', 'weekend_rule_adjustment': 'previous_working_day',
            'billing_rule': 'full_charge', 'customer_po_amount': order.amount_total,
        })
        order.action_confirm()
        row = order.billing_engine_line_ids
        self.assertEqual(len(row), 1)
        self.assertEqual(row.total_days, 30)
        self.assertEqual(row.rental_start, date(2026, 1, 14))
        self.assertEqual(row.rental_end, date(2026, 2, 13))
        self.assertEqual(row.invoice_date, date(2026, 2, 6))
        self.assertEqual(self.partner.rental_default_billing_rule, 'prorate')
        self.assertEqual(self.partner.rental_default_weekend_rule_adjustment, 'next_working_day')

    def test_confirmed_orders_keep_existing_amendment_rules(self):
        order = self.order_model.create(self._values(state='sale'))
        before = self._settings(order)
        order._onchange_rental_customer_billing_defaults()
        self.assertEqual(self._settings(order), before)
        self.assertFalse(order.billing_settings_changed)
        order.top_billing = 'didepan'
        self.assertTrue(order.billing_settings_changed)
        order.action_generate_billing_engine()
        self.assertTrue(order.billing_engine_regenerated)
        with self.assertRaises(UserError):
            order.top_billing = 'dibelakang'

    def test_copy_preserves_saved_overrides_not_latest_customer_defaults(self):
        order = self.order_model.create(self._values(
            top_billing='didepan', weekend_rule_adjustment='keep_original', billing_rule='full_charge',
        ))
        copied = order.copy()
        self.assertEqual(self._settings(copied), self._settings(order))

    def test_ordinary_sales_orders_do_not_receive_customer_rental_settings(self):
        order = self.order_model.create(self._values(is_rental_order=False))
        self.assertFalse(order.is_rental_order)
        self.assertFalse(order.top_billing)
        self.assertFalse(order.billing_rule)
        self.assertEqual(order.weekend_rule_adjustment, 'keep_original')

    def test_rpc_generated_quotation_also_uses_customer_defaults(self):
        province = self.env.ref('x_rental_profit_calculation.prov_dki')
        city = self.env['rpc.kota'].create({'name': 'Rental Default Test City', 'provinsi_id': province.id})
        parameters = {
            field: self.env['rpc.parameter'].create({
                'name': 'Rental Default Test ' + parameter_type, 'parameter_type': parameter_type,
            }).id
            for field, parameter_type in (
                ('type_of_klien_id', 'type_of_klien'), ('jenis_transaksi_id', 'jenis_transaksi'),
                ('tujuan_id', 'tujuan'), ('sumber_id', 'sumber'), ('sumber_daya_id', 'sumber_daya'),
                ('jenis_kendaraan_id', 'jenis_kendaraan'), ('pemakaian_id', 'pemakaian'), ('merek_id', 'merek'),
            )
        }
        document = self.env['rpc.document'].create({
            **parameters, 'partner_id': self.partner.id,
            'provinsi_id': province.id, 'kota_id': city.id,
            'type_kendaraan_id': self.product.id, 'tahun_mulai_sewa': 2026,
            'masa_sewa': 12, 'jumlah_unit': 1,
            'term_of_payment_due': 'addm', 'term_of_payment_hari': 30,
            'sewa_per_bulan_batas_atas': 3000000, 'sewa_per_bulan_batas_bawah': 3000000,
            'state': 'approved', 'final_rental_price_type': 'lower', 'final_rental_price': 3000000,
        })
        action = document.action_create_combined_quotation()
        order = self.order_model.browse(action['res_id'])
        self.assertTrue(order.is_rental_order)
        self.assertEqual(order.state, 'draft')
        self.assertEqual(self._settings(order), self.partner._rental_order_billing_defaults())


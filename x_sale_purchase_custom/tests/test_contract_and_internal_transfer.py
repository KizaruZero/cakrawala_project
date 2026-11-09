# -*- coding: utf-8 -*-
import base64
from datetime import date
import io
import zipfile
from unittest.mock import patch
from dateutil.relativedelta import relativedelta
from lxml import etree

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged
from odoo.tests.common import new_test_user

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestRentalContractAndInternalTransfer(RentalBillingEngineInvoiceCommon):
    """Tests for Tasks 1, 2, 3 (Contract Number, Period, Reminder, Contract List) and Task 4 (Internal Transfer)."""

    def _extract_docx_text(self, b64_content):
        raw = base64.b64decode(b64_content)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            xml_bytes = zf.read('word/document.xml')
        root = etree.fromstring(xml_bytes)
        return ''.join(root.itertext())

    def test_task1_contract_number_default_editable_and_period_validation(self):
        order = self._order()
        # Upon confirmation, contract_start_date and contract_end_date default from rental period
        self.assertTrue(order.contract_start_date)
        self.assertTrue(order.contract_end_date)
        self.assertFalse(order.contract_number)

        # Clicking Create Contract fills contract_number from generated Word number
        order.action_create_contract()
        self.assertTrue(order.contract_number)
        self.assertFalse(order.contract_number.lower().startswith('no.'))
        self.assertIn('PS/CRS/', order.contract_number)
        self.assertTrue(order.contract_file)

        docx_text_1 = self._extract_docx_text(order.contract_file)
        self.assertIn(f"No.{order.contract_number}", docx_text_1)
        self.assertNotIn("No.No.", docx_text_1)

        # User edits contract_number and Periode Kontrak, then clicks Create Contract again
        order.write({
            'contract_number': '0888/PKS-CUSTOM/XI/2026',
            'contract_start_date': date(2026, 11, 1),
            'contract_end_date': date(2027, 10, 31),
        })
        order.action_create_contract()
        self.assertEqual(order.contract_number, '0888/PKS-CUSTOM/XI/2026')
        docx_text_2 = self._extract_docx_text(order.contract_file)
        self.assertIn('No.0888/PKS-CUSTOM/XI/2026', docx_text_2)
        self.assertNotIn('No.No.', docx_text_2)

        # End date earlier than start date must raise ValidationError
        with self.assertRaises(ValidationError):
            order.write({
                'contract_start_date': date(2027, 5, 10),
                'contract_end_date': date(2027, 5, 1),
            })

    def test_task2_contract_expiration_email_reminder_to_salesperson(self):
        salesperson = new_test_user(
            self.env,
            login='salesperson_contract_reminder',
            groups='sales_team.group_sale_salesman',
            name='Budi Salesperson',
            email='budi.sales@cakrawala.test',
        )
        today = fields.Date.today()

        order_1m = self._order(user_id=salesperson.id, notify_contract_expiration='1_month')
        order_1m.write({
            'contract_number': 'S00901PS/CRS/XI/2026',
            'contract_start_date': today - relativedelta(months=11),
            'contract_end_date': today + relativedelta(months=1),
        })
        self.assertEqual(order_1m.contract_notification_status, 'scheduled')

        order_future = self._order(user_id=salesperson.id, notify_contract_expiration='7_days')
        order_future.write({
            'contract_number': 'S00902PS/CRS/XI/2026',
            'contract_start_date': today,
            'contract_end_date': today + relativedelta(days=20),
        })

        before_mails = self.env['mail.mail'].sudo().search([('model', '=', 'sale.order'), ('res_id', '=', order_1m.id)])
        self.env['sale.order']._cron_check_contract_expiration()
        after_mails = self.env['mail.mail'].sudo().search([('model', '=', 'sale.order'), ('res_id', '=', order_1m.id)]) - before_mails

        self.assertTrue(order_1m.is_contract_expiration_notified)
        self.assertEqual(order_1m.contract_expiration_notified_date, today)
        self.assertEqual(order_1m.contract_notification_status, 'notified')
        self.assertEqual(len(after_mails), 1)
        self.assertIn('budi.sales@cakrawala.test', after_mails.email_to or '')
        self.assertIn('S00901PS/CRS/XI/2026', after_mails.subject or '')

        # Order not yet within 7_days threshold is NOT notified
        self.assertFalse(order_future.is_contract_expiration_notified)

        # Extending contract_end_date resets notification flag so next expiration will notify again
        order_1m.write({'contract_end_date': today + relativedelta(months=6)})
        self.assertFalse(order_1m.is_contract_expiration_notified)
        self.assertEqual(order_1m.contract_notification_status, 'scheduled')

        # Quotation order (state='draft') remains 'no_schedule' and is NOT notified until confirmed
        order_draft = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_rental_order': True,
            'state': 'draft',
            'user_id': salesperson.id,
            'notify_contract_expiration': '7_days',
            'contract_number': 'DRAFT001/CRS/XI/2026',
            'contract_start_date': today - relativedelta(months=5),
            'contract_end_date': today + relativedelta(days=7),
        })
        self.assertEqual(order_draft.contract_notification_status, 'no_schedule')
        self.env['sale.order']._cron_check_contract_expiration()
        self.assertFalse(order_draft.is_contract_expiration_notified)

    def test_two_month_selection_preserves_default_and_email_label(self):
        model = self.env['sale.order']
        choices = dict(model._fields['notify_contract_expiration'].selection)
        self.assertEqual(choices['2_months'], '2 Month Before')
        self.assertEqual(model.default_get(['notify_contract_expiration'])['notify_contract_expiration'], '1_month')
        self.assertTrue({'1_month', '2_weeks', '7_days'}.issubset(choices))
        order = self._order(notify_contract_expiration='2_months')
        template = self.env.ref('x_sale_purchase_custom.mail_template_rental_contract_expiration')
        rendered = template._render_field('body_html', order.ids)[order.id]
        self.assertIn('2 Month Before', rendered)

    def test_two_month_reminder_threshold_single_send_and_reset(self):
        order = self._order(notify_contract_expiration='2_months')
        order.write({
            'contract_start_date': date(2027, 1, 1),
            'contract_end_date': date(2028, 3, 31),
        })
        self.env.user.email = 'two.month.reminder@cakrawala.test'
        order.user_id = self.env.user
        template = self.env.ref('x_sale_purchase_custom.mail_template_rental_contract_expiration')
        with patch.object(type(template), 'send_mail', return_value=1) as send:
            with patch.object(fields.Date, 'today', return_value=date(2028, 1, 30)):
                self.env['sale.order']._cron_check_contract_expiration()
            self.assertFalse(order.is_contract_expiration_notified)
            send.assert_not_called()
            with patch.object(fields.Date, 'today', return_value=date(2028, 1, 31)):
                self.env['sale.order']._cron_check_contract_expiration()
                self.env['sale.order']._cron_check_contract_expiration()
            self.assertTrue(order.is_contract_expiration_notified)
            self.assertEqual(order.contract_expiration_notified_date, date(2028, 1, 31))
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args.args[0], order.id)
        order.notify_contract_expiration = '1_month'
        self.assertFalse(order.is_contract_expiration_notified)
        self.assertFalse(order.contract_expiration_notified_date)

    def test_two_month_reminder_clamps_to_leap_year_month_end(self):
        order = self._order(notify_contract_expiration='2_months')
        order.write({
            'contract_start_date': date(2027, 1, 1),
            'contract_end_date': date(2028, 4, 30),
        })
        with patch.object(fields.Date, 'today', return_value=date(2028, 2, 28)):
            self.env['sale.order']._cron_check_contract_expiration()
        self.assertFalse(order.is_contract_expiration_notified)
        with patch.object(fields.Date, 'today', return_value=date(2028, 2, 29)), \
                patch.object(type(self.env['mail.template']), 'send_mail', return_value=1):
            self.env['sale.order']._cron_check_contract_expiration()
        self.assertTrue(order.is_contract_expiration_notified)
        self.assertEqual(order.contract_expiration_notified_date, date(2028, 2, 29))

    def test_task3_contract_list_menu_and_view_columns(self):
        menu = self.env.ref('x_sale_purchase_custom.menu_rental_contract_list')
        parent_menu = self.env.ref('sale_renting.rental_order_menu')
        action = self.env.ref('x_sale_purchase_custom.action_rental_contract_list')
        list_view = self.env.ref('x_sale_purchase_custom.view_rental_contract_list')

        self.assertEqual(menu.parent_id, parent_menu)
        self.assertEqual(menu.name, 'Contract List')
        self.assertEqual(menu.action, action)

        root = etree.fromstring(list_view.arch_db.encode())
        field_names = root.xpath('//list/field/@name')
        for expected in (
            'name',
            'contract_number',
            'contract_start_date',
            'contract_end_date',
            'user_id',
            'notify_contract_expiration',
            'contract_notification_status',
        ):
            self.assertIn(expected, field_names)

    def test_task4_customer_payment_internal_transfer_destination_coa(self):
        bank_account = self.env['account.account'].create({
            'name': 'BCA PLUIT 789 COA',
            'code': '11017890',
            'account_type': 'asset_cash',
            'company_ids': [Command.set(self.company.ids)],
        })
        bank_journal = self.env['account.journal'].create({
            'name': 'BCA PLUIT 789',
            'code': 'BC789',
            'type': 'bank',
            'default_account_id': bank_account.id,
            'company_id': self.company.id,
        })
        # Simulate Odoo 19 Enterprise bank journal where payment_account_id is empty
        bank_journal.inbound_payment_method_line_ids.write({'payment_account_id': False})
        bank_journal.outbound_payment_method_line_ids.write({'payment_account_id': False})

        refund_insurance_coa = self.env['account.account'].create({
            'name': 'Klaim / Refund Asuransi',
            'code': '42009911',
            'account_type': 'income_other',
            'company_ids': [Command.set(self.company.ids)],
        })

        # 1. Receive (Uang Masuk) Internal Transfer from Customer Payments menu context
        ctx = {
            'default_payment_type': 'inbound',
            'default_partner_type': 'customer',
        }
        with Form(self.env['account.payment'].with_context(**ctx)) as pay_form:
            self.assertEqual(pay_form.payment_type_ui, 'inbound')
            pay_form.payment_type_ui = 'internal_transfer'
            self.assertTrue(pay_form.is_internal_transfer_custom)
            self.assertEqual(pay_form.internal_transfer_direction, 'inbound')
            pay_form.partner_id = self.partner
            pay_form.journal_id = bank_journal
            pay_form.custom_destination_account_id = refund_insurance_coa
            pay_form.amount = 20000000.0
            pay_form.memo = 'Terima refund asuransi'
            payment_in = pay_form.save()

        self.assertTrue(payment_in.is_internal_transfer_custom)
        self.assertEqual(payment_in.payment_type, 'inbound')
        self.assertEqual(payment_in.destination_account_id, refund_insurance_coa)
        self.assertEqual(payment_in.outstanding_account_id, bank_account)

        payment_in.action_post()
        self.assertTrue(payment_in.move_id)
        self.assertEqual(payment_in.move_id.state, 'posted')

        bank_line = payment_in.move_id.line_ids.filtered(lambda l: l.account_id == bank_account)
        dest_line = payment_in.move_id.line_ids.filtered(lambda l: l.account_id == refund_insurance_coa)
        self.assertEqual(len(bank_line), 1)
        self.assertEqual(len(dest_line), 1)
        self.assertEqual(bank_line.debit, 20000000.0)
        self.assertEqual(bank_line.credit, 0.0)
        self.assertEqual(dest_line.credit, 20000000.0)
        self.assertEqual(dest_line.debit, 0.0)

        # 2. Send (Uang Keluar) Internal Transfer without partner_id
        other_bank_coa = self.env['account.account'].create({
            'name': 'Mandiri Operasional COA',
            'code': '11018888',
            'account_type': 'asset_cash',
            'company_ids': [Command.set(self.company.ids)],
        })
        with Form(self.env['account.payment'].with_context(**ctx)) as out_form:
            out_form.payment_type_ui = 'internal_transfer'
            out_form.internal_transfer_direction = 'outbound'
            out_form.journal_id = bank_journal
            out_form.custom_destination_account_id = other_bank_coa
            out_form.amount = 5000000.0
            out_form.memo = 'Mutasi antar rekening'
            payment_out = out_form.save()

        payment_out.action_post()
        self.assertTrue(payment_out.move_id)
        self.assertEqual(payment_out.move_id.state, 'posted')
        out_bank_line = payment_out.move_id.line_ids.filtered(lambda l: l.account_id == bank_account)
        out_dest_line = payment_out.move_id.line_ids.filtered(lambda l: l.account_id == other_bank_coa)
        self.assertEqual(out_bank_line.credit, 5000000.0)
        self.assertEqual(out_dest_line.debit, 5000000.0)

        # 3. Same account validation check
        with self.assertRaises(ValidationError):
            self.env['account.payment'].create({
                'payment_type_ui': 'internal_transfer',
                'internal_transfer_direction': 'inbound',
                'journal_id': bank_journal.id,
                'custom_destination_account_id': bank_account.id,
                'amount': 100000.0,
            })

    def test_batch2_rpc_quotation_description_crm_tahun_and_approved_sync(self):
        # Setup parameters and location for CRM Lead & RPC
        province = self.env.ref('x_rental_profit_calculation.prov_dki')
        city = self.env['rpc.kota'].create({
            'name': 'Jakarta Selatan Test',
            'provinsi_id': province.id,
        })
        params = {
            field: self.env['rpc.parameter'].create({
                'name': 'Batch2 Test ' + ptype,
                'parameter_type': ptype,
            }).id
            for field, ptype in (
                ('client_type_id', 'type_of_klien'),
                ('tujuan_id', 'tujuan'),
                ('jenis_transaksi_id', 'jenis_transaksi'),
                ('custom_source_id', 'sumber'),
                ('sumber_daya_id', 'sumber_daya'),
                ('jenis_kendaraan_id', 'jenis_kendaraan'),
                ('penggunaan_kendaraan_id', 'penggunaan_kendaraan'),
                ('pemakaian', 'pemakaian'),
            )
        }
        vehicle = self.env['product.product'].create({
            'name': 'DAIHATSU GRANMAX BLINDVAN 1.3 AC MT',
            'is_vehicle': True,
            'sale_ok': True,
            'purchase_ok': True,
        })
        offering_stage = self.env['crm.stage'].search([('name', '=', 'Offering')], limit=1)
        if not offering_stage:
            offering_stage = self.env['crm.stage'].create({'name': 'Offering', 'sequence': 20})

        lead = self.env['crm.lead'].create({
            'name': 'Opportunity Granmax 2025',
            'type': 'opportunity',
            'stage_id': offering_stage.id,
            'partner_id': self.partner.id,
            'contact_name': 'PIC Granmax',
            'job_position': 'Fleet Manager',
            'email_from': 'pic.granmax@example.test',
            'phone': '+628123456789',
            'state_id': province.id,
            'city_id': city.id,
            'merek_id': vehicle.product_tmpl_id.id,
            'tipe_kendaraan_id': vehicle.id,
            'tahun': '2025',
            'quantity': 3,
            'masa_sewa': 24,
            'sewa_per_bulan': 4000000.0,
            'harga_otr': 180000000.0,
            **params,
        })

        # Task 2 Verification: tahun on crm.lead is preserved and mapped to rpc.document.tahun_kendaraan
        self.assertEqual(lead.tahun, '2025')
        rpc_action = lead.action_create_rpc()
        rpc = self.env['rpc.document'].browse(rpc_action['res_id'])
        self.assertEqual(rpc.crm_lead_id, lead)
        self.assertEqual(rpc.tahun_kendaraan, 2025)

        # Configure RPC values and approve it
        rpc.write({
            'harga_otr': 195000000.0,
            'discount': 6400000.0,
            'discount_dikapitalisasi': 'yes',
            'masa_sewa': 36,
            'sewa_per_bulan_batas_atas': 4500000.0,
            'sewa_per_bulan_batas_bawah': 4200000.0,
        })
        self.assertAlmostEqual(rpc.otr_final, 188600000.0)
        # Before RPC is approved, CRM Lead still holds initial values
        self.assertEqual(lead.sewa_per_bulan, 4000000.0)
        self.assertEqual(lead.harga_otr, 180000000.0)
        self.assertEqual(lead.masa_sewa, 24)

        # Task 3 Verification: When RPC becomes fully approved, CRM Lead fields auto-populate
        rpc.write({
            'final_rental_price_type': 'upper',
            'final_rental_price': 4300000.0,
            'state': 'approved',
        })
        lead.invalidate_recordset()
        self.assertAlmostEqual(lead.sewa_per_bulan, 4300000.0)
        self.assertAlmostEqual(lead.harga_otr, 188600000.0)
        self.assertEqual(lead.masa_sewa, 36)
        self.assertAlmostEqual(lead.total_forecast, 4300000.0 * 36)

        # Task 1 Verification: Create Quotation from RPC does NOT include RPC number in Description
        quo_action = rpc.action_create_quotation()
        quotation = self.env['sale.order'].browse(quo_action['res_id'])
        self.assertEqual(len(quotation.input_line_ids), 1)
        input_line = quotation.input_line_ids[0]
        self.assertEqual(input_line.rpc_document_id, rpc)
        self.assertNotIn(rpc.name, input_line.name)
        self.assertEqual(input_line.name, vehicle.display_name)

        quotation.action_generate_order_lines()
        self.assertEqual(len(quotation.order_line), 3)
        for sol in quotation.order_line:
            self.assertNotIn(rpc.name, sol.name)
        self.assertEqual(
            quotation._find_rpc_document(input_line.product_id, input_line.name),
            rpc,
        )



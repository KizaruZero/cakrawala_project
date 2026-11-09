from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


MODULE = 'x_rental_profit_calculation'


@tagged('post_install', '-at_install')
class TestRpcProcurementAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={
            **cls.env.context, 'tracking_disable': True,
            'mail_create_nosubscribe': True,
        })
        cls.users = {
            role: new_test_user(
                cls.env, login=f'rpc_submit_access_{role}',
                name=f'RPC Submit {role}',
                groups=f'base.group_user,{MODULE}.group_rpc_{role}',
            )
            for role in ('marketing', 'procurement', 'operation', 'finance', 'manager')
        }
        cls.internal_user = new_test_user(
            cls.env, login='rpc_submit_access_internal', groups='base.group_user',
        )
        cls.partner = cls.env['res.partner'].create({'name': 'RPC Role Test Customer'})
        cls.province = cls.env.ref(f'{MODULE}.prov_dki')
        cls.city = cls.env['rpc.kota'].create({
            'name': 'RPC Role Test City', 'provinsi_id': cls.province.id,
        })
        cls.parameters = {
            field: cls.env['rpc.parameter'].create({
                'name': 'RPC Role Test ' + parameter_type,
                'parameter_type': parameter_type,
            }).id
            for field, parameter_type in (
                ('type_of_klien_id', 'type_of_klien'),
                ('jenis_transaksi_id', 'jenis_transaksi'),
                ('tujuan_id', 'tujuan'), ('sumber_id', 'sumber'),
                ('sumber_daya_id', 'sumber_daya'),
                ('jenis_kendaraan_id', 'jenis_kendaraan'),
                ('pemakaian_id', 'pemakaian'), ('merek_id', 'merek'),
            )
        }

    def _document(self, **values):
        return self.env['rpc.document'].create({
            **self.parameters, 'partner_id': self.partner.id,
            'provinsi_id': self.province.id, 'kota_id': self.city.id,
            'tahun_mulai_sewa': 2026, 'masa_sewa': 36, 'jumlah_unit': 1,
            'term_of_payment_due': 'addb', 'term_of_payment_hari': 30,
            'sewa_per_bulan_batas_atas': 10000000,
            'sewa_per_bulan_batas_bawah': 9000000,
            'harga_otr': 450000000, 'state': 'submitted', **values,
        })

    def test_button_requires_procurement_while_draft_submit_stays_marketing(self):
        view = self.env.ref(f'{MODULE}.view_rpc_document_form')
        arch = etree.fromstring(view.arch_db)
        buttons = arch.xpath('//header/button[@name="action_procurement_submit"]')
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].get('groups'), f'{MODULE}.group_rpc_procurement')
        self.assertEqual(buttons[0].get('invisible'), "state != 'submitted'")
        marketing = arch.xpath('//header/button[@name="action_submit"]')[0]
        self.assertEqual(marketing.get('groups'), f'{MODULE}.group_rpc_marketing')

    def test_procurement_without_marketing_can_submit_and_audit_actor(self):
        user = self.users['procurement']
        self.assertFalse(user.has_group(f'{MODULE}.group_rpc_marketing'))
        document = self._document()
        delegated = document.with_user(user)
        self.assertFalse(delegated.env.su)
        delegated.action_procurement_submit()
        self.assertEqual(document.state, 'procurement_done')
        self.assertIn(user.name, str(document.message_ids[:1].body))

    def test_other_roles_cannot_call_submit_even_directly(self):
        for user in (self.users['marketing'], self.users['operation'], self.users['finance'], self.internal_user):
            with self.subTest(user=user.login):
                document = self._document()
                before_messages = document.message_ids
                with self.assertRaisesRegex(UserError, 'role RPC'):
                    document.with_user(user).action_procurement_submit()
                self.assertEqual(document.state, 'submitted')
                self.assertEqual(document.message_ids, before_messages)

    def test_rpc_manager_retains_access_through_implied_procurement_role(self):
        user = self.users['manager']
        self.assertTrue(user.has_group(f'{MODULE}.group_rpc_procurement'))
        document = self._document()
        document.with_user(user).action_procurement_submit()
        self.assertEqual(document.state, 'procurement_done')

    def test_rpc_roles_selector_enables_procurement_without_marketing(self):
        group = self.env.ref(f'{MODULE}.group_rpc_procurement')
        self.internal_user.rpc_role_ids = [Command.set(group.ids)]
        self.assertTrue(self.internal_user.has_group(f'{MODULE}.group_rpc_procurement'))
        self.assertFalse(self.internal_user.has_group(f'{MODULE}.group_rpc_marketing'))
        document = self._document()
        document.with_user(self.internal_user).action_procurement_submit()
        self.assertEqual(document.state, 'procurement_done')

    def test_state_and_positive_otr_guards_are_preserved(self):
        draft = self._document(state='draft')
        with self.assertRaisesRegex(UserError, 'Submitted'):
            draft.with_user(self.users['procurement']).action_procurement_submit()
        self.assertEqual(draft.state, 'draft')
        zero_price = self._document(harga_otr=0)
        with self.assertRaisesRegex(UserError, 'Harga OTR'):
            zero_price.with_user(self.users['procurement']).action_procurement_submit()
        self.assertEqual(zero_price.state, 'submitted')

    def test_all_workflow_buttons_match_their_department_in_form_list_and_wizards(self):
        expected = {
            'action_submit': 'marketing',
            'action_procurement_submit': 'procurement',
            'action_operation_submit': 'operation',
            'action_finance_start': 'finance',
            'action_confirm': 'finance',
            'action_approve': 'manager',
            'action_open_revise_wizard': 'manager',
            'action_reset_draft': 'manager',
            'action_create_quotation': 'marketing',
            'action_create_combined_quotation': 'marketing',
            'action_confirm_revise': 'manager',
            'action_approve_final_price': 'manager',
            'action_reject': 'manager',
        }
        found = set()
        for view_name in (
            'view_rpc_document_form', 'view_rpc_document_list',
            'view_rpc_document_revise_wizard_form',
            'view_rpc_final_rental_price_wizard_form',
        ):
            arch = etree.fromstring(self.env.ref(f'{MODULE}.{view_name}').arch_db)
            for button in arch.xpath('//button[@name]'):
                action = button.get('name')
                if action in expected:
                    found.add(action)
                    self.assertEqual(button.get('groups'), f'{MODULE}.group_rpc_{expected[action]}', action)
        self.assertEqual(found, set(expected))

    def test_every_mutating_workflow_action_rejects_other_roles_including_aliases(self):
        actions = {
            'action_submit': 'marketing',
            'action_procurement_submit': 'procurement',
            'action_operation_submit': 'operation',
            'action_finance_start': 'finance',
            'action_confirm': 'finance',
            'action_finance_submit': 'finance',
            'action_approve': 'manager',
            'action_open_revise_wizard': 'manager',
            'action_cancel': 'manager',
            'action_reset_draft': 'manager',
            'action_create_quotation': 'marketing',
            'action_create_combined_quotation': 'marketing',
        }
        document = self._document()
        before = document.read(['state', 'quotation_ids', 'message_ids', 'final_rental_price'])
        for action, role in actions.items():
            for user in [*self.users.values(), self.internal_user]:
                if user.has_group(f'{MODULE}.group_rpc_{role}'):
                    continue
                with self.subTest(action=action, user=user.login):
                    self.assertFalse(document.with_user(user).env.su)
                    with self.assertRaisesRegex(UserError, 'role RPC'):
                        getattr(document.with_user(user), action)()
                    self.assertEqual(document.read(['state', 'quotation_ids', 'message_ids', 'final_rental_price']), before)

    def test_effective_form_and_list_remove_buttons_for_users_outside_the_role(self):
        expected = {
            'action_submit': 'marketing',
            'action_procurement_submit': 'procurement',
            'action_operation_submit': 'operation',
            'action_finance_start': 'finance',
            'action_confirm': 'finance',
            'action_approve': 'manager',
            'action_open_revise_wizard': 'manager',
            'action_reset_draft': 'manager',
            'action_create_quotation': 'marketing',
            'action_create_combined_quotation': 'marketing',
        }
        for user in [*self.users.values(), self.internal_user]:
            for view_type in ('form', 'list'):
                view = self.env.ref(f'{MODULE}.view_rpc_document_{view_type}')
                result = self.env['rpc.document'].with_user(user).get_view(view.id, view_type)
                arch = etree.fromstring(result['arch'])
                for action, role in expected.items():
                    if (action == 'action_create_combined_quotation') != (view_type == 'list'):
                        continue
                    with self.subTest(user=user.login, action=action):
                        buttons = arch.xpath(f'//button[@name="{action}"]')
                        self.assertEqual(bool(buttons), user.has_group(f'{MODULE}.group_rpc_{role}'))

    def test_operation_only_user_can_submit_operation_without_procurement(self):
        user = self.users['operation']
        self.assertFalse(user.has_group(f'{MODULE}.group_rpc_procurement'))
        document = self._document(
            state='procurement_done', biaya_towing=700000,
            replacement_car_qty=30, resale_value_rate=0.65,
        )
        document.with_user(user).action_operation_submit()
        self.assertEqual(document.state, 'operation_done')
        self.assertIn(user.name, str(document.message_ids[:1].body))

    def test_marketing_only_user_can_submit_marketing(self):
        employee = self.env['hr.employee'].create({
            'name': 'RPC Marketing Submit Test', 'user_id': self.users['marketing'].id,
        })
        vehicle = self.env['product.product'].create({'name': 'RPC Workflow Test Vehicle'})
        document = self._document(
            state='draft', marketing_id=employee.id, pembuat_rpc_id=employee.id,
            type_kendaraan_id=vehicle.id, tahun_kendaraan=2026,
        )
        document.with_user(self.users['marketing']).action_submit()
        self.assertEqual(document.state, 'submitted')

    def test_finance_only_user_can_start_finance(self):
        document = self._document(state='operation_done')
        document.with_user(self.users['finance']).action_finance_start()
        self.assertEqual(document.state, 'finance_done')

    def test_finance_internal_sync_does_not_grant_manual_master_crud(self):
        user = self.users['finance']
        groups_before = user.group_ids
        document = self._document(state='operation_done').with_user(user)
        document.action_finance_start()
        self.assertFalse(document.env.su)
        self.assertTrue(document.logic_table_ids)
        self.assertEqual(user.group_ids, groups_before)
        self.assertFalse(user.has_group(f'{MODULE}.group_rpc_manager'))
        h1 = self.env['rpc.funding.hierarchy.1'].create({'name': 'ACL Test H1'})
        h2 = self.env['rpc.funding.hierarchy.2'].create({
            'name': 'ACL Test H2', 'hierarchy_1_id': h1.id,
        })
        h3 = self.env['rpc.funding.hierarchy.3'].create({
            'name': 'ACL Test H3', 'hierarchy_2_id': h2.id,
        })
        for master, create_values in (
            (h1, {'name': 'Finance manual H1'}),
            (h2, {'name': 'Finance manual H2', 'hierarchy_1_id': h1.id}),
            (h3, {'name': 'Finance manual H3', 'hierarchy_2_id': h2.id}),
        ):
            with self.subTest(model=master._name):
                self.assertTrue(master.with_user(user).read(['name']))
                with self.assertRaises(AccessError), self.cr.savepoint():
                    self.env[master._name].with_user(user).create(create_values)
                with self.assertRaises(AccessError), self.cr.savepoint():
                    master.with_user(user).write({'sequence': 999})
                with self.assertRaises(AccessError), self.cr.savepoint():
                    master.with_user(user).unlink()
                master.with_user(self.users['manager']).write({'sequence': 20})
                self.assertEqual(master.sequence, 20)

    def test_internal_sync_updates_existing_and_archived_masters_without_duplicates(self):
        document = self._document(state='finance_done').with_user(self.users['finance'])
        logic = self.env['rpc.hierarchy.logic'].search([('active', '=', True)], limit=1)
        first = document._sync_funding_hierarchy_chain(logic)
        for master in first:
            master.sudo(False).with_user(self.users['manager']).write({'active': False, 'sequence': 999})
        second = document._sync_funding_hierarchy_chain(logic)
        self.assertEqual([master.id for master in second], [master.id for master in first])
        for master, source in zip(second, (logic.hierarchy_id, logic.cost_group_code_id, logic.cost_group_name_id)):
            self.assertTrue(master.active)
            self.assertEqual(master.sequence, source.sequence)
        before = {model: self.env[model].with_context(active_test=False).search_count([]) for model in (
            'rpc.funding.hierarchy.1', 'rpc.funding.hierarchy.2', 'rpc.funding.hierarchy.3',
        )}
        document._sync_funding_hierarchy_chain(logic)
        for model, count in before.items():
            self.assertEqual(self.env[model].with_context(active_test=False).search_count([]), count)

    def test_non_finance_roles_cannot_enter_elevated_internal_sync(self):
        document = self._document()
        logic = self.env['rpc.hierarchy.logic'].search([('active', '=', True)], limit=1)
        h1_count = self.env['rpc.funding.hierarchy.1'].with_context(active_test=False).search_count([])
        for user in (self.users['marketing'], self.users['procurement'], self.users['operation'], self.internal_user):
            target = document.with_user(user)
            with self.subTest(user=user.login):
                with self.assertRaisesRegex(UserError, 'role RPC'):
                    target._funding_hierarchy_sync_models()
                with self.assertRaisesRegex(UserError, 'role RPC'):
                    target._sync_funding_hierarchy_chain(logic)
                with self.assertRaisesRegex(UserError, 'role RPC'):
                    target._sync_summary_hierarchy('Not authorized', False, 10)
        self.assertEqual(self.env['rpc.funding.hierarchy.1'].with_context(active_test=False).search_count([]), h1_count)

    def test_internal_sync_checks_rpc_write_record_rules_before_elevation(self):
        document = self._document(state='finance_done')
        self.env['ir.rule'].create({
            'name': 'RPC Finance cannot write this test document',
            'model_id': self.env['ir.model']._get_id('rpc.document'),
            'groups': [Command.link(self.env.ref(f'{MODULE}.group_rpc_finance').id)],
            'domain_force': f"[('id', '!=', {document.id})]",
            'perm_read': False, 'perm_write': True,
            'perm_create': False, 'perm_unlink': False,
        })
        with self.assertRaises(AccessError):
            document.with_user(self.users['finance'])._funding_hierarchy_sync_models()

    def test_finance_can_confirm_after_internal_sync_without_manager_role(self):
        bank, installment_type = self.env['rpc.parameter'].create([
            {'name': 'Finance ACL Test Bank', 'parameter_type': 'leasing_bank'},
            {'name': 'ADDB', 'code': 'ADDB', 'parameter_type': 'jenis_angsuran'},
        ])
        document = self._document(
            state='operation_done', leasing_bank_id=bank.id,
            jenis_angsuran_id=installment_type.id, masa_kredit=36,
            down_payment_pct=0.1, bunga_pct=0.05,
            opex_pusat_pct=0.04, cost_of_fund_pct=0.15,
            insurance_type='crs',
            insurance_kategori_id=self.env.ref(f'{MODULE}.kategori_4').id,
        ).with_user(self.users['finance'])
        document.action_finance_start()
        document.action_confirm()
        self.assertEqual(document.state, 'waiting_approval')
        self.assertTrue(document.next_approval_stage_id)
        self.assertTrue(document.insurance_line_ids)
        self.assertFalse(document.env.su)
        self.assertFalse(self.users['finance'].has_group(f'{MODULE}.group_rpc_manager'))

    def test_manager_can_revise_and_reset_but_reset_still_requires_cancelled(self):
        manager = self.users['manager']
        document = self._document()
        action = document.with_user(manager).action_open_revise_wizard()
        self.assertEqual(action['res_model'], 'rpc.document.revise.wizard')
        wizard = self.env['rpc.document.revise.wizard'].with_user(manager).create({
            'document_id': document.id, 'revise_reason': 'Authorized manager revision',
        })
        wizard.action_confirm_revise()
        self.assertEqual(document.state, 'draft')
        with self.assertRaisesRegex(UserError, 'Cancelled'):
            document.with_user(manager).action_reset_draft()
        cancelled = self._document(state='cancelled')
        cancelled.with_user(manager).action_reset_draft()
        self.assertEqual(cancelled.state, 'draft')

    def test_revision_helper_and_wizard_cannot_bypass_manager_requirement(self):
        document = self._document()
        wizard = self.env['rpc.document.revise.wizard'].create({
            'document_id': document.id, 'revise_reason': 'Not allowed',
        })
        for user in (self.users['marketing'], self.users['procurement'], self.users['operation'], self.users['finance']):
            with self.subTest(user=user.login):
                with self.assertRaisesRegex(UserError, 'role RPC'):
                    document.with_user(user)._revise_to_draft('Not allowed')
                with self.assertRaisesRegex(UserError, 'role RPC'):
                    wizard.with_user(user).action_confirm_revise()
                self.assertEqual(document.state, 'submitted')

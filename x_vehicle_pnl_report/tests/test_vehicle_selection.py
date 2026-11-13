from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestVehiclePnlSelection(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.company_code = 'PNLQA'
        cls.plan, _other_plans = cls.env['account.analytic.plan']._get_all_plans()
        cls.Wizard = cls.env['vehicle.pnl.report.wizard']
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'PnL Selection QA'})
        cls.model = cls.env['fleet.vehicle.model'].create({'name': 'PnL Vehicle QA', 'brand_id': brand.id})
        cls.leased = cls.env['fleet.vehicle.state'].create({'name': 'Leased PnL QA'})
        cls.inactive = cls.env['fleet.vehicle.state'].create({'name': 'Inactive PnL QA'})
        cls.retired = cls.env['fleet.vehicle.state'].create({'name': 'Retired PnL QA'})
        cls.income = cls.env['account.account'].create({
            'name': 'Pendapatan Sewa PnL QA', 'code': '79999701', 'account_type': 'income',
            'company_ids': [Command.set(cls.company.ids)],
        })
        cls.expense = cls.env['account.account'].create({
            'name': 'Servis PnL QA', 'code': '79999702', 'account_type': 'expense',
            'company_ids': [Command.set(cls.company.ids)],
        })

    def _account(self, name, **values):
        return self.env['account.analytic.account'].create({
            'name': name, 'plan_id': self.plan.id, 'company_id': self.company.id, **values,
        })

    def _transaction(self, analytic, amount=1000, **values):
        return self.env['account.analytic.line'].create({
            'name': 'Vehicle PnL Selection QA', 'account_id': analytic.id,
            'date': fields.Date.today(), 'amount': amount,
            'company_id': analytic.company_id.id or self.company.id, **values,
        })

    def _vehicle(self, plate, state=None, active=True, transact=True, company=None):
        company = company or self.company
        analytic = self._account('Analytic ' + plate, company_id=company.id)
        if transact:
            self._transaction(analytic)
        vehicle = self.env['fleet.vehicle'].create({
            'model_id': self.model.id, 'license_plate': plate, 'company_id': company.id,
            'state_id': (state or self.leased).id, 'fleet_sub_status_id': False,
            'analytic_account_id': analytic.id, 'active': active,
        })
        return vehicle, analytic

    def _ids(self, wizard=None):
        vehicles, _accounts = (wizard if wizard is not None else self.Wizard)._get_eligible_vehicles()
        return vehicles.ids

    def test_all_fleet_statuses_and_archives_with_transactions_are_included(self):
        vehicles = self.env['fleet.vehicle']
        for index, (state, active) in enumerate((
                (self.leased, True), (self.inactive, True),
                (self.retired, True), (self.inactive, False))):
            vehicle, _analytic = self._vehicle('B %s PNL' % (1000 + index), state=state, active=active)
            vehicles |= vehicle
        self.assertTrue(set(vehicles.ids).issubset(self._ids()))
        no_state, _analytic = self._vehicle('B 1005 PNL')
        no_state.write({'state_id': False, 'fleet_sub_status_id': False})
        self.assertIn(no_state.id, self._ids())

    def test_archived_analytic_account_with_transactions_is_included(self):
        vehicle, analytic = self._vehicle('B 1006 PNL', active=False, state=self.inactive)
        analytic.active = False
        vehicles, accounts = self.Wizard._get_eligible_vehicles()
        self.assertIn(vehicle, vehicles)
        self.assertIn(analytic, accounts)
        self.assertEqual(self.Wizard._resolve_analytic_account_for_vehicle(vehicle, accounts), analytic)

    def test_vehicles_without_analytic_items_or_analytic_account_are_included(self):
        for active in (True, False):
            vehicle, _analytic = self._vehicle('B %s NOITEM' % int(active), active=active, transact=False)
            self.assertIn(vehicle.id, self._ids())
        no_analytic = self.env['fleet.vehicle'].create({
            'model_id': self.model.id, 'license_plate': 'B 2 NOANALYTIC',
            'company_id': self.company.id, 'state_id': self.leased.id, 'fleet_sub_status_id': False,
        })
        no_analytic.analytic_account_id = False
        self.assertIn(no_analytic.id, self._ids())

    def test_zero_amount_item_still_counts_as_existing_analytic_transaction(self):
        vehicle, analytic = self._vehicle('B 1007 PNL', active=False, transact=False)
        self._transaction(analytic, amount=0)
        self.assertIn(vehicle.id, self._ids())

    def test_duplicate_direct_and_reverse_matches_produce_one_vehicle(self):
        vehicle, analytic = self._vehicle('B 1008 PNL', active=False)
        self.assertEqual(analytic.vehicle_id, vehicle)
        self.assertEqual(self._ids().count(vehicle.id), 1)

    def test_reverse_link_finds_archived_vehicle_when_direct_link_is_empty(self):
        vehicle, analytic = self._vehicle('B 1009 PNL', active=False)
        vehicle.analytic_account_id = False
        self.assertEqual(analytic.vehicle_id, vehicle)
        self.assertFalse(vehicle.analytic_account_id)
        vehicles, accounts = self.Wizard._get_eligible_vehicles()
        self.assertIn(vehicle, vehicles)
        self.assertEqual(self.Wizard._resolve_analytic_account_for_vehicle(vehicle, accounts), analytic)

    def test_plate_fallback_finds_archived_vehicle_and_archived_analytic(self):
        # Historical plate-only linkage: create the account before the vehicle
        # so the automatic fleet backlinks do not exist in this fixture.
        analytic = self._account('Legacy plate PnL', license_plate='B 1010 PNL')
        self._transaction(analytic)
        vehicle = self.env['fleet.vehicle'].create({
            'model_id': self.model.id, 'license_plate': 'B 1010 PNL',
            'company_id': self.company.id, 'active': False,
            'state_id': self.inactive.id, 'fleet_sub_status_id': False,
        })
        analytic.active = False
        self.assertFalse(analytic.vehicle_id)
        self.assertFalse(vehicle.analytic_account_id)
        vehicles, accounts = self.Wizard._get_eligible_vehicles()
        self.assertIn(vehicle, vehicles)
        self.assertEqual(self.Wizard._resolve_analytic_account_for_vehicle(vehicle, accounts), analytic)
        self.assertEqual(self.Wizard._resolve_analytic_account_for_vehicle(vehicle), analytic)

    def test_default_get_contains_archived_and_does_not_reactivate_sources(self):
        vehicle, analytic = self._vehicle('B 1011 PNL', active=False, state=self.inactive)
        analytic.active = False
        self.env.flush_all()
        vehicle_before = vehicle.read(['active', 'state_id', 'analytic_account_id', 'write_date'])
        analytic_before = analytic.read(['active', 'name', 'write_date'])
        defaults = self.Wizard.default_get(['line_ids', 'date_to'])
        values = [command[2] for command in defaults['line_ids']]
        self.assertEqual([value['vehicle_id'] for value in values], [vehicle.id])
        self.assertEqual(values[0]['analytic_account_id'], analytic.id)
        self.assertEqual(vehicle.read(list(vehicle_before[0])), vehicle_before)
        self.assertEqual(analytic.read(list(analytic_before[0])), analytic_before)

    def test_search_preserves_selected_archived_vehicle_and_clearing_query_restores_all(self):
        archived, analytic = self._vehicle('B 1012 PNL', active=False, state=self.inactive)
        current, _other = self._vehicle('B 1013 PNL')
        wizard = self.Wizard.create({})
        wizard.line_ids.filtered(lambda line: line.vehicle_id == archived).selected = True
        wizard.search_query = current.license_plate.lower()
        wizard._onchange_search_query()
        self.assertEqual(set(wizard.line_ids.vehicle_id.ids), {archived.id, current.id})
        self.assertEqual(wizard.line_ids.filtered('selected').vehicle_id, archived)
        wizard.search_query = 'not-matching'
        wizard._onchange_search_query()
        self.assertEqual(wizard.line_ids.vehicle_id, archived)
        wizard.search_query = False
        wizard._onchange_search_query()
        self.assertEqual(set(wizard.line_ids.vehicle_id.ids), {archived.id, current.id})
        self.assertEqual(wizard.line_ids.filtered('selected').analytic_account_id, analytic)

    def test_search_by_analytic_name_or_code_includes_archived_vehicle(self):
        archived, analytic = self._vehicle('B 1014 PNL', active=False)
        self._vehicle('B 1015 PNL')
        analytic.write({'name': 'HISTORYUNITPNL', 'code': 'HISTPNL42'})
        for query in ('historyunitpnl', 'histpnl42'):
            wizard = self.Wizard.create({'search_query': query})
            wizard._onchange_search_query()
            self.assertEqual(wizard.line_ids.vehicle_id, archived)

    def test_native_wizard_form_can_search_and_save_archived_vehicle(self):
        archived, analytic = self._vehicle('B 1016 PNL', active=False)
        self._vehicle('B 1017 PNL')
        with Form(self.Wizard) as form:
            form.search_query = archived.license_plate
        self.assertEqual(form.record.line_ids.vehicle_id, archived)
        self.assertEqual(form.record.line_ids.analytic_account_id, analytic)

    def test_selected_companies_only_and_no_sudo_fallback_for_record_rules(self):
        own, _analytic = self._vehicle('B 1018 PNL', active=False)
        other = self.env['res.company'].create({'name': 'PnL Other Company', 'company_code': 'PNL2'})
        foreign, _foreign_analytic = self._vehicle('B 1019 PNL', active=False, company=other)
        self.assertIn(own.id, self._ids())
        self.assertNotIn(foreign.id, self._ids())
        both = self.Wizard.with_context(allowed_company_ids=(self.company | other).ids)
        self.assertTrue({own.id, foreign.id}.issubset(self._ids(both)))
        user = new_test_user(self.env, login='pnl_selection_accounting',
                             groups='account.group_account_user,fleet.fleet_group_user,analytic.group_analytic_accounting',
                             company_id=self.company.id)
        self.assertIn(own.id, self._ids(self.Wizard.with_user(user)))
        self.env['ir.rule'].create({
            'name': 'PnL test excludes own vehicle', 'model_id': self.env['ir.model']._get_id('fleet.vehicle'),
            'domain_force': "[('id', '!=', %s)]" % own.id,
        })
        self.assertNotIn(own.id, self._ids(self.Wizard.with_user(user)))

    def test_vehicle_listed_even_when_analytic_items_are_hidden_by_record_rules(self):
        vehicle, _analytic = self._vehicle('B 1020 PNL', active=False)
        user = new_test_user(self.env, login='pnl_selection_analytic_rule',
                             groups='account.group_account_user,fleet.fleet_group_user,analytic.group_analytic_accounting',
                             company_id=self.company.id)
        self.env['ir.rule'].create({
            'name': 'PnL test no readable analytic items',
            'model_id': self.env['ir.model']._get_id('account.analytic.line'),
            'domain_force': "[('id', '=', 0)]",
        })
        vehicles, accounts = self.Wizard.with_user(user)._get_eligible_vehicles()
        self.assertIn(vehicle, vehicles)
        self.assertFalse(accounts)

    def test_archived_selection_reaches_preview_pdf_action_and_existing_report_totals(self):
        archived, analytic = self._vehicle('B 1021 PNL', active=False, transact=False)
        analytic.active = False
        self._transaction(analytic, amount=1000, general_account_id=self.income.id)
        self._transaction(analytic, amount=-250, general_account_id=self.expense.id)
        wizard = self.Wizard.create({})
        wizard.line_ids.filtered(lambda line: line.vehicle_id == archived).selected = True
        self.assertEqual(wizard.action_preview_report()['report_type'], 'qweb-html')
        self.assertEqual(wizard.action_print_report()['report_type'], 'qweb-pdf')
        parser = self.env['report.x_vehicle_pnl_report.report_vehicle_pnl_document']
        data = parser._get_report_values(wizard.ids)['reports_data']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['vehicle'], archived)
        self.assertEqual(data[0]['total_pendapatan'], 1000)
        self.assertEqual(data[0]['total_biaya'], 250)
        self.assertEqual(data[0]['total_pendapatan_biaya'], 750)
        html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'x_vehicle_pnl_report.report_vehicle_pnl_document', wizard.ids)
        self.assertIn(archived.license_plate.encode(), html)
        self.assertFalse(archived.active)

    def test_preview_and_print_still_require_checkbox_selection(self):
        self._vehicle('B 1022 PNL', active=False)
        wizard = self.Wizard.create({})
        for action in (wizard.action_preview_report, wizard.action_print_report):
            with self.assertRaisesRegex(UserError, 'minimal satu kendaraan'):
                action()

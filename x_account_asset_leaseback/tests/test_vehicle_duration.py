from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from odoo.addons.account_asset.tests.common import TestAccountAssetCommon


class _RollbackCheck(Exception):
    pass


@tagged("post_install", "-at_install")
class TestVehicleDurationDefaults(TestAccountAssetCommon):

    @classmethod
    def _create_company(cls, **values):
        if "company_code" in cls.env["res.company"]._fields:
            values.setdefault("company_code", "DURQA")
        return super()._create_company(**values)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Selecting Vehicle requires native Fleet read access as well as the
        # Accounting test role. Do not sudo the behavior under test.
        cls.env.user.sudo().group_ids |= cls.env.ref("fleet.fleet_group_user")
        cls.asset_model = cls.create_asset(
            value=0, periodicity="monthly", periods=60, state="model", name="Duration Model")
        cls.fleet_model = cls.asset_model.copy({"name": "Duration Fleet Model", "x_is_fleet": True})
        plan = cls.env["account.analytic.plan"].sudo().create({"name": "Duration Vehicles"})
        cls.analytic = cls.env["account.analytic.account"].create({
            "name": "Duration Vehicle Analytic", "plan_id": plan.id,
            "company_id": cls.env.company.id,
        })
        brand = cls.env["fleet.vehicle.model.brand"].sudo().create({"name": "Duration QA"})
        cls.vehicle_model = cls.env["fleet.vehicle.model"].sudo().create({
            "name": "Duration QA Vehicle", "brand_id": brand.id,
        })
        cls.vehicle = cls._vehicle("B 9600 DUR")

    @classmethod
    def _vehicle(cls, plate):
        return cls.env["fleet.vehicle"].sudo().create({
            "model_id": cls.vehicle_model.id, "license_plate": plate,
            "company_id": cls.env.company.id, "analytic_account_id": cls.analytic.id,
        })

    def _new_asset(self, **values):
        return self.env["account.asset"].create({
            "name": "Duration QA Asset", "model_id": self.asset_model.id,
            "account_asset_id": self.asset_model.account_asset_id.id,
            "account_depreciation_id": self.asset_model.account_depreciation_id.id,
            "account_depreciation_expense_id": self.asset_model.account_depreciation_expense_id.id,
            "journal_id": self.asset_model.journal_id.id,
            "original_value": 960000, "acquisition_date": "2026-01-01",
            "method_period": "1", "prorata_computation_type": "none", **values,
        })

    def _history(self, duration, vehicle=None, total_duration=None, **values):
        # Keep source duration and remaining months different in every fixture
        # so copying the wrong field cannot accidentally pass the regressions.
        asset = self._new_asset(
            vehicle_id=(vehicle or self.vehicle).id,
            method_number=total_duration if total_duration is not None else duration + 12,
            leaseback_remaining_duration=duration, **values)
        asset.write({"state": "close", "active": False})
        return asset

    def _refinancing_marker(self, asset, kind):
        self.env["account.move"].create({
            "asset_id": asset.id, "journal_id": asset.journal_id.id,
            "date": "2026-01-31", "move_type": "entry",
            "asset_move_type": "disposal" if kind == "dispose" else "sale",
            "x_refinancing_type": kind,
        })
        asset.state = kind
        self.assertEqual(asset.x_refinancing_type, kind)
        self.assertEqual(asset.state, kind)

    def test_create_without_duration_uses_archived_vehicle_history(self):
        previous = self._history(96)
        before = previous.read(["state", "active", "method_number", "original_value"])
        asset = self._new_asset(vehicle_id=self.vehicle.id)
        self.assertEqual(asset.method_number, 96)
        self.assertEqual(asset.method_period, "1")
        self.assertFalse(asset.depreciation_move_ids)
        self.assertEqual(previous.read(["state", "active", "method_number", "original_value"]), before)

    def test_latest_creation_not_acquisition_or_last_edit(self):
        first = self._history(72, acquisition_date="2026-10-01")
        latest = self._history(96, acquisition_date="2020-01-01")
        first.name = "Edited after the newer asset"
        asset = self._new_asset(vehicle_id=self.vehicle.id)
        self.assertEqual(asset.method_number, latest.leaseback_remaining_duration)
        self.assertEqual(asset.method_number, 96)

    def test_creation_date_has_priority_over_id(self):
        first = self._history(72)
        second = self._history(96)
        self.env.cr.execute("UPDATE account_asset SET create_date = %s WHERE id = %s",
                            ("2026-01-02", first.id))
        self.env.cr.execute("UPDATE account_asset SET create_date = %s WHERE id = %s",
                            ("2026-01-01", second.id))
        self.assertEqual(self._new_asset(vehicle_id=self.vehicle.id).method_number, 72)

    def test_remaining_duration_is_copied_not_original_full_duration(self):
        old = self._history(84, total_duration=96)
        self.assertEqual(self._new_asset(vehicle_id=self.vehicle.id).method_number, 84)
        self.assertEqual(old.method_number, 96)
        self.assertEqual(old.leaseback_remaining_duration, 84)

    def test_latest_zero_remaining_is_not_replaced_by_full_or_older_duration(self):
        self._history(84, total_duration=96)
        latest = self._history(0, total_duration=72)
        self.assertEqual(self._new_asset(vehicle_id=self.vehicle.id).method_number, 0)
        self.assertEqual(latest.method_number, 72)

    def test_unfilled_remaining_field_does_not_fall_back_to_full_duration(self):
        old = self._new_asset(vehicle_id=self.vehicle.id, method_number=96)
        old.write({"state": "close", "active": False})
        self.assertEqual(old.leaseback_remaining_duration, 0)
        asset = self._new_asset(method_number=60)
        asset.vehicle_id = self.vehicle
        self.assertEqual(asset.method_number, 0)

    def test_model_and_gross_increase_are_not_history_sources(self):
        old = self._history(96)
        self.asset_model.copy({"vehicle_id": self.vehicle.id, "method_number": 120})
        self._new_asset(vehicle_id=self.vehicle.id, method_number=144, parent_id=old.id)
        self.assertEqual(self._new_asset(vehicle_id=self.vehicle.id).method_number, 96)

    def test_explicit_duration_and_context_default_remain_authoritative(self):
        self._history(96)
        asset = self._new_asset(vehicle_id=self.vehicle.id, method_number=72)
        self.assertEqual(asset.method_number, 72)
        asset.write({"state": "close", "active": False})
        contextual = self.env["account.asset"].with_context(default_method_number=36)
        values = self._new_asset().copy_data()[0]
        values.update(vehicle_id=self.vehicle.id)
        values.pop("method_number", None)
        self.assertEqual(contextual.create(values).method_number, 36)

    def test_api_vehicle_context_default_is_supported(self):
        self._history(96)
        values = self._new_asset().copy_data()[0]
        values.pop("method_number", None)
        values.pop("vehicle_id", None)
        asset = self.env["account.asset"].with_context(default_vehicle_id=self.vehicle.id).create(values)
        self.assertEqual(asset.vehicle_id, self.vehicle)
        self.assertEqual(asset.method_number, 96)

    def test_no_history_keeps_native_default_and_clearing_vehicle_keeps_input(self):
        asset = self._new_asset(vehicle_id=self.vehicle.id)
        native_default = self.env["account.asset"].default_get(["method_number"])["method_number"]
        self.assertEqual(asset.method_number, native_default)
        asset.method_number = 72
        asset.vehicle_id = False
        self.assertEqual(asset.method_number, 72)

    def test_selecting_vehicle_on_saved_draft_uses_history_and_excludes_self(self):
        previous = self._history(96)
        asset = self._new_asset(method_number=60)
        asset.vehicle_id = self.vehicle
        self.assertEqual(asset.method_number, 96)
        asset.method_number = 72
        asset._onchange_vehicle_duration_from_previous_asset()
        self.assertEqual(asset.method_number, previous.leaseback_remaining_duration)

    def test_selecting_other_vehicle_gets_its_own_latest_duration(self):
        second_vehicle = self._vehicle("B 7200 DUR")
        self._history(96)
        self._history(72, vehicle=second_vehicle)
        asset = self._new_asset(vehicle_id=self.vehicle.id)
        asset.vehicle_id = second_vehicle
        self.assertEqual(asset.method_number, 72)
        asset.write({"vehicle_id": self.vehicle.id, "method_number": 48})
        self.assertEqual(asset.method_number, 48)

    def test_form_autofill_then_manual_override_is_saved(self):
        self._history(84, total_duration=96)
        with Form(self.env["account.asset"]) as form:
            form.name = "Manual Duration Form"
            form.model_id = self.fleet_model
            form.original_value = 960000
            form.acquisition_date = "2026-01-01"
            form.vehicle_id = self.vehicle
            self.assertEqual(form.method_number, 84)
            form.method_number = 72
        self.assertEqual(form.record.method_number, 72)

    def test_model_defaults_do_not_override_selected_vehicle_duration(self):
        self._history(96)
        with Form(self.env["account.asset"]) as form:
            form.name = "Model Duration Form"
            form.model_id = self.fleet_model
            form.original_value = 960000
            form.vehicle_id = self.vehicle
            form.model_id = self.fleet_model.copy({
                "name": "Another Fleet Model", "method_number": 48, "x_is_fleet": True})
            self.assertEqual(form.method_number, 96)

    def test_running_asset_duration_does_not_change_on_vehicle_assignment(self):
        self._history(96)
        asset = self._new_asset(method_number=12)
        asset.validate()
        original_moves = asset.depreciation_move_ids
        before = original_moves.read(["date", "state", "depreciation_value"])
        asset.vehicle_id = self.vehicle
        self.assertEqual(asset.method_number, 12)
        self.assertEqual(asset.depreciation_move_ids, original_moves)
        self.assertEqual(original_moves.read(["date", "state", "depreciation_value"]), before)

    def test_changed_default_invalidates_only_unposted_draft_board(self):
        previous = self._history(96)
        asset = self._new_asset(method_number=12)
        asset.compute_depreciation_board()
        self.assertTrue(asset.depreciation_move_ids)
        self.assertFalse(asset.depreciation_move_ids.filtered(lambda move: move.state == "posted"))
        asset.vehicle_id = self.vehicle
        self.assertEqual(asset.method_number, 96)
        self.assertFalse(asset.depreciation_move_ids)
        self.assertEqual(previous.method_number, 108)
        self.assertEqual(previous.leaseback_remaining_duration, 96)

    def test_draft_with_posted_history_is_not_automatically_recalculated(self):
        self._history(96)
        asset = self._new_asset(method_number=12)
        asset.validate()
        asset.state = "draft"
        before = asset.depreciation_move_ids.read(["date", "state", "depreciation_value"])
        asset.vehicle_id = self.vehicle
        self.assertEqual(asset.method_number, 12)
        self.assertEqual(asset.depreciation_move_ids.read(["date", "state", "depreciation_value"]), before)

    def test_second_running_main_asset_is_blocked_on_create_write_and_confirm(self):
        running = self._new_asset(vehicle_id=self.vehicle.id, method_number=96)
        running.state = "open"
        with self.assertRaisesRegex(ValidationError, "A vehicle can only own one asset"), self.env.cr.savepoint():
            self._new_asset(vehicle_id=self.vehicle.id, state="open")
        draft = self._new_asset(method_number=60, state="open")
        with self.assertRaisesRegex(ValidationError, "A vehicle can only own one asset"), self.env.cr.savepoint():
            draft.vehicle_id = self.vehicle
        second = self._new_asset(vehicle_id=self.vehicle.id, method_number=60)
        self.assertEqual(second.state, "draft")
        with self.assertRaisesRegex(ValidationError, "A vehicle can only own one asset"), self.env.cr.savepoint():
            second.state = "open"

    def test_non_running_assets_do_not_block_a_second_asset(self):
        old = self._new_asset(vehicle_id=self.vehicle.id, method_number=96)
        # Draft + Draft on the same vehicle is allowed.
        self._new_asset(vehicle_id=self.vehicle.id, method_number=60).unlink()
        for state in ("close", "leaseback", "sell", "dispose"):
            if state == "close":
                old.state = state
            else:
                self._refinancing_marker(old, state)
            # Roll back after each state so the next loop starts from one asset.
            with self.assertRaises(_RollbackCheck), self.env.cr.savepoint():
                new = self._new_asset(vehicle_id=self.vehicle.id, method_number=60)
                new.state = "open"
                self.assertEqual(new.vehicle_id, self.vehicle)
                raise _RollbackCheck()

    def test_native_archive_policy_and_fleet_confirm_requirements_are_not_relaxed(self):
        asset = self._new_asset(vehicle_id=self.vehicle.id, method_number=96)
        self._refinancing_marker(asset, "leaseback")
        with self.assertRaisesRegex(UserError, "cannot archive"), self.env.cr.savepoint():
            asset.active = False
        missing_vehicle = self._new_asset(model_id=self.fleet_model.id)
        with self.assertRaisesRegex(ValidationError, "Vehicle is required"), self.env.cr.savepoint():
            missing_vehicle.validate()

    def test_no_cross_company_history_lookup(self):
        old = self._history(96)
        other = self._create_company(name="Duration Other Company")
        self.assertFalse(self.env["account.asset"]._latest_vehicle_duration_asset(self.vehicle.id, other.id))
        self.assertEqual(self.env["account.asset"]._latest_vehicle_duration_asset(
            self.vehicle.id, old.company_id.id), old)

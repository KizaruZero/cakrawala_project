from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.account_asset.tests.common import TestAccountAssetCommon


@tagged("post_install", "-at_install")
class TestAssetRefinancing(TestAccountAssetCommon):
    """The disposal baseline of a refinanced asset.

    Closing an asset through a leaseback / sell / dispose adds entries to the
    depreciation board: a prorata depreciation dated on the closing date, then
    the disposal entry itself. Downstream disposal flows must read their values
    from the last *normal* depreciation booked before that, not from the latest
    board entry.

    The figures mirror the reference case: 417.000.000 over 60 months, so
    6.950.000 a month, leased back three days after the 8th depreciation.
    """

    LEASEBACK_DATE = "2020-09-03"
    LAST_NORMAL_DATE = "2020-08-31"

    @classmethod
    def _create_company(cls, **create_values):
        # Other addons of this database make extra company fields mandatory.
        if "company_code" in cls.env["res.company"]._fields:
            create_values.setdefault("company_code", "TST")
        return super()._create_company(**create_values)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ar_account = cls.company_data["default_account_receivable"]
        cls.deferred_account = cls.company_data["default_account_revenue"].copy({
            "code": "501409",
            "name": "Laba Rugi Ditangguhkan",
            "is_deferred_pl_account": True,
        })

    def _create_running_asset(self):
        """A 417.000.000 asset depreciated monthly over 60 months."""
        asset = self.create_asset(
            value=417000000,
            periodicity="monthly",
            periods=60,
            acquisition_date="2020-01-01",
        )
        asset.validate()
        asset.depreciation_move_ids.filtered(lambda move: move.state == "draft")._post()
        return asset

    def _leaseback(self, asset, date=None, ar_amount=360705000):
        return asset.set_to_close_leaseback(
            ar_account=self.ar_account,
            ar_amount=ar_amount,
            deferred_account=self.deferred_account,
            date=fields.Date.from_string(date or self.LEASEBACK_DATE),
        )

    def test_asset_without_refinancing_keeps_previous_behaviour(self):
        asset = self._create_running_asset()

        self.assertFalse(asset.x_is_refinanced)
        self.assertFalse(asset.x_refinancing_type)
        self.assertFalse(asset.x_refinancing_move_id)
        self.assertFalse(asset.x_pre_refinancing_move_id)
        self.assertEqual(asset._get_refinancing_reference_values(), {})

    def test_leaseback_flags_the_asset_and_its_prorata_entry(self):
        asset = self._create_running_asset()
        self._leaseback(asset)

        self.assertTrue(asset.x_is_refinanced)
        self.assertEqual(asset.x_refinancing_type, "leaseback")
        self.assertEqual(asset.x_refinancing_date, fields.Date.from_string(self.LEASEBACK_DATE))
        self.assertEqual(asset.x_refinancing_move_id.asset_move_type, "sale")
        self.assertEqual(asset.x_refinancing_move_id.x_refinancing_type, "leaseback")

        adjustments = asset.depreciation_move_ids.filtered("x_is_refinancing_adjustment")
        self.assertTrue(adjustments, "the closing must book a prorata depreciation")
        self.assertEqual(
            set(adjustments.mapped("date")),
            {fields.Date.from_string(self.LEASEBACK_DATE)},
        )
        self.assertEqual(set(adjustments.mapped("asset_move_type")), {"depreciation"})
        self.assertNotIn(asset.x_refinancing_move_id, adjustments)

    def test_disposal_values_come_from_the_last_normal_depreciation(self):
        asset = self._create_running_asset()
        self._leaseback(asset)

        reference = asset.x_pre_refinancing_move_id
        self.assertEqual(reference.date, fields.Date.from_string(self.LAST_NORMAL_DATE))
        self.assertFalse(reference.x_is_refinancing_adjustment)

        values = asset._get_refinancing_reference_values()
        self.assertEqual(values["reference_move_id"], reference.id)
        self.assertEqual(values["monthly_depreciation"], 6950000)
        self.assertEqual(values["accumulated_depreciation"], 55600000)
        self.assertEqual(values["book_value"], 361400000)

    def test_entries_sharing_the_refinancing_date_are_not_selected(self):
        """Case 4: the date alone cannot order the board."""
        asset = self._create_running_asset()
        self._leaseback(asset)

        leaseback_date = fields.Date.from_string(self.LEASEBACK_DATE)
        same_date_entries = asset.depreciation_move_ids.filtered(
            lambda move: move.date == leaseback_date and move.state != "cancel"
        )
        self.assertGreaterEqual(len(same_date_entries), 2)
        self.assertIn(asset.x_refinancing_move_id, same_date_entries)
        self.assertNotIn(asset.x_pre_refinancing_move_id, same_date_entries)
        self.assertLess(asset.x_pre_refinancing_move_id.date, leaseback_date)

    def test_duplicate_carries_no_refinancing_history(self):
        asset = self._create_running_asset()
        self._leaseback(asset, ar_amount=400000000)
        self.assertTrue(asset.leaseback_deferred_pl_amount)

        copied = asset.copy()
        self.assertFalse(copied.leaseback_deferred_pl_amount)
        self.assertFalse(copied.x_is_refinanced)
        self.assertFalse(copied.x_refinancing_type)
        self.assertFalse(copied.x_refinancing_move_id)
        self.assertFalse(copied.x_pre_refinancing_move_id)
        self.assertEqual(copied._get_refinancing_reference_values(), {})

    def test_latest_refinancing_drives_the_reference(self):
        """Case 3: several refinancing events on the same asset."""
        asset = self._create_running_asset()
        self._leaseback(asset)
        first_event = asset.x_refinancing_move_id

        later_event = self.env["account.move"].create({
            "asset_id": asset.id,
            "date": fields.Date.from_string("2020-12-31"),
            "journal_id": asset.journal_id.id,
            "move_type": "entry",
            "asset_move_type": "sale",
            "x_refinancing_type": "sell",
        })

        self.assertNotEqual(first_event, later_event)
        self.assertEqual(asset.x_refinancing_move_id, later_event)
        self.assertEqual(asset.x_refinancing_type, "sell")
        self.assertLess(asset.x_pre_refinancing_move_id.date, later_event.date)


@tagged("post_install", "-at_install")
class TestOneAssetPerVehicle(TestAssetRefinancing):
    """A vehicle owns exactly one asset."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "vehicle_id" not in cls.env["account.asset"]._fields:
            import unittest
            raise unittest.SkipTest("account_asset_fleet is not installed")
        cls.vehicle = cls._make_vehicle(cls, "B 4321 ONE")

    def _make_vehicle(self, license_plate, analytic=None):
        return self.env["fleet.vehicle"].sudo().create({
            "model_id": self.env["fleet.vehicle.model"].sudo().search([], limit=1).id,
            "license_plate": license_plate,
            "analytic_account_id": analytic.id if analytic else False,
        })

    def test_second_asset_on_the_same_vehicle_is_refused(self):
        asset = self._create_running_asset()
        asset.vehicle_id = self.vehicle

        other = self._create_running_asset()
        with self.assertRaises(ValidationError):
            other.vehicle_id = self.vehicle

    def test_duplicate_starts_detached_from_the_vehicle(self):
        asset = self._create_running_asset()
        asset.write({
            "vehicle_id": self.vehicle.id,
            "analytic_distribution": {str(self._analytic_account().id): 100},
        })

        copied = asset.copy()
        self.assertFalse(copied.vehicle_id)
        self.assertFalse(copied.analytic_distribution)

    def test_archived_asset_frees_the_vehicle(self):
        asset = self._create_running_asset()
        asset.vehicle_id = self.vehicle
        # Odoo only allows archiving a closed asset.
        self._leaseback(asset)
        asset.active = False

        replacement = self._create_running_asset()
        replacement.vehicle_id = self.vehicle
        self.assertEqual(replacement.vehicle_id, self.vehicle)

    def _analytic_account(self):
        plan = self.env["account.analytic.plan"].search([], limit=1)
        return self.env["account.analytic.account"].create({
            "name": "Vehicle analytic",
            "plan_id": plan.id,
        })


@tagged("post_install", "-at_install")
class TestFleetAssetModel(TestOneAssetPerVehicle):
    """An asset built on a fleet asset model must name its vehicle."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.analytic = cls._make_analytic_account(cls)
        cls.vehicle.sudo().analytic_account_id = cls.analytic
        cls.fleet_model = cls._create_running_asset_model(cls, is_fleet=True)
        cls.plain_model = cls._create_running_asset_model(cls, is_fleet=False)

    def _make_analytic_account(self):
        plan = self.env["account.analytic.plan"].sudo().search([], limit=1)
        return self.env["account.analytic.account"].create({
            "name": "Vehicle 4321 analytic",
            "plan_id": plan.id,
        })

    def _create_running_asset_model(self, is_fleet):
        model = self.create_asset(value=0, periodicity="monthly", periods=60)
        model.write({"state": "model", "x_is_fleet": is_fleet})
        return model

    def test_asset_inherits_the_flag_from_its_model(self):
        asset = self._create_running_asset()
        asset.model_id = self.plain_model
        self.assertFalse(asset.x_is_fleet)

        asset.vehicle_id = self.vehicle
        asset.model_id = self.fleet_model
        self.assertTrue(asset.x_is_fleet)

    def test_fleet_asset_without_vehicle_is_refused(self):
        asset = self._create_running_asset()
        with self.assertRaises(ValidationError):
            asset.model_id = self.fleet_model

    def test_vehicle_fills_the_analytic_distribution(self):
        asset = self._create_running_asset()
        asset.vehicle_id = self.vehicle
        self.assertEqual(asset.analytic_distribution, {str(self.analytic.id): 100.0})

        asset.model_id = self.fleet_model
        self.assertTrue(asset.x_is_fleet)

    def test_duplicate_lands_in_draft_and_keeps_its_model(self):
        asset = self._create_running_asset()
        asset.vehicle_id = self.vehicle
        asset.model_id = self.fleet_model

        copied = asset.copy()
        self.assertEqual(copied.state, "draft")
        self.assertEqual(copied.model_id, self.fleet_model)
        self.assertTrue(copied.x_is_fleet)
        self.assertFalse(copied.vehicle_id)
        self.assertFalse(copied.analytic_distribution)

    def test_duplicate_cannot_start_running_without_its_own_vehicle(self):
        asset = self._create_running_asset()
        asset.vehicle_id = self.vehicle
        asset.model_id = self.fleet_model
        copied = asset.copy()

        with self.assertRaises(ValidationError):
            copied.validate()

        copied.vehicle_id = self._make_vehicle("B 9999 TWO", self._make_analytic_account())
        copied.validate()
        self.assertEqual(copied.state, "open")

    def test_running_fleet_asset_cannot_lose_its_vehicle(self):
        asset = self._create_running_asset()
        asset.vehicle_id = self.vehicle
        asset.model_id = self.fleet_model

        with self.assertRaises(ValidationError):
            asset.vehicle_id = False

    def test_non_fleet_asset_still_needs_no_vehicle(self):
        asset = self._create_running_asset()
        asset.model_id = self.plain_model
        self.assertFalse(asset.vehicle_id)

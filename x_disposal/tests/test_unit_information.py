import unittest
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDisposalUnitInformation(TransactionCase):
    """Unit Information of a bidding, sourced from the vehicle's asset.

    The asset link is resolved by name (vehicle asset number), and the
    depreciation figures come from ``x_account_asset_leaseback`` when the asset
    has already been refinanced.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "account.asset" not in cls.env.registry:
            raise unittest.SkipTest("account_asset is not installed")

        cls.company = cls.env.company
        cls.asset_account = cls._find_account(("asset_fixed", "asset_non_current", "asset_current"))
        cls.expense_account = cls._find_account(("expense",))
        cls.receivable_account = cls._find_account(("asset_receivable",))
        cls.journal = cls.env["account.journal"].search([
            ("type", "=", "general"), ("company_id", "=", cls.company.id),
        ], limit=1)
        if not (cls.asset_account and cls.expense_account and cls.receivable_account and cls.journal):
            raise unittest.SkipTest("no chart of accounts available on this database")

        cls.vehicle = cls.env["fleet.vehicle"].create({
            "model_id": cls.env["fleet.vehicle.model"].search([], limit=1).id,
            "license_plate": "B 1235 PSU",
            "asset_number": "TEST-DISPOSAL-ASSET",
        })
        cls.bidding = cls.env["disposal.bidding"].create({"vehicle_id": cls.vehicle.id})

    @classmethod
    def _find_account(cls, account_types):
        return cls.env["account.account"].search([
            ("account_type", "in", list(account_types)),
            ("company_ids", "in", cls.company.ids),
        ], limit=1)

    def _create_asset(self, acquisition_date, original_value=417000000, periods=60):
        accounting = {
            "account_asset_id": self.asset_account.id,
            "account_depreciation_id": self.asset_account.id,
            "account_depreciation_expense_id": self.expense_account.id,
            "journal_id": self.journal.id,
            "prorata_computation_type": "none",
            "method_number": periods,
            "method_period": "1",
            "method": "linear",
        }
        model = self.env["account.asset"].create({"name": "Test Disposal Model", "state": "model", **accounting})
        return self.env["account.asset"].create({
            "name": self.vehicle.asset_number,
            "model_id": model.id,
            "acquisition_date": acquisition_date,
            "original_value": original_value,
            "salvage_value": 0,
            **accounting,
        })

    def _create_document(self, vehicle, name, location, **type_vals):
        document_type = self.env["fleet.service.type"].create({
            "name": name, "category": "contract", **type_vals,
        })
        document = self.env["fleet.vehicle.log.contract"].create({
            "vehicle_id": vehicle.id,
            "cost_subtype_id": document_type.id,
            "bpkb_location": location,
        })
        # A new document always starts as New, whatever the values say.
        document.write({"state": "open"})
        self.assertEqual(document.state, "open")
        return document

    def test_bpkb_location_is_filled_when_the_vehicle_is_chosen(self):
        self._create_document(self.vehicle, "BPKB Disposal", "Solo", is_bpkb=True, is_license_plate=False)
        other = self.vehicle.copy({"license_plate": "B 1236 PSU", "asset_number": "TEST-DISPOSAL-OTHER"})
        self._create_document(other, "BPKB Other", "Jakarta", is_bpkb=True, is_license_plate=False)

        bidding = self.env["disposal.bidding"].create({"vehicle_id": self.vehicle.id})
        self.assertEqual(bidding.disposal_bpkb_location, "Solo")

        with Form(self.env["disposal.bidding"]) as form:
            form.vehicle_id = other
            form.start_date = "2026-11-01"
            form.end_date = "2026-11-30"
            self.assertEqual(form.disposal_bpkb_location, "Jakarta")
        self.assertEqual(form.record.disposal_bpkb_location, "Jakarta")

    def test_draft_form_requires_both_dates(self):
        for dates in ({}, {"start_date": "2026-11-01"}, {"end_date": "2026-11-30"}):
            form = Form(self.env["disposal.bidding"])
            form.vehicle_id = self.vehicle
            for name, value in dates.items():
                setattr(form, name, value)
            with self.assertRaises(AssertionError):
                form.save()

    def test_approved_bidding_without_dates_stays_valid_in_form(self):
        self.bidding.with_context(x_disposal_post_approval=True).write({"state": "approved"})
        self.assertFalse(self.bidding.start_date)
        Form(self.bidding).save()

    def test_submit_is_refused_without_both_dates(self):
        partner = self.env["res.partner"].create({"name": "Bidder"})
        self.bidding.write({
            "open_price": 1000,
            "bidding_line_ids": [(0, 0, {"partner_id": partner.id, "bidding_price": 1000})],
        })
        for dates in (
            {"start_date": False, "end_date": False},
            {"start_date": "2026-11-01", "end_date": False},
            {"start_date": False, "end_date": "2026-11-30"},
        ):
            self.bidding.write(dates)
            with self.assertRaisesRegex(ValidationError, "Start Date and End Date"):
                self.bidding.action_submit_for_approval()
            self.assertEqual(self.bidding.state, "draft")

        self.bidding.write({"start_date": "2026-11-01", "end_date": "2026-11-30"})
        self.bidding._check_submission_requirements()

    def test_bpkb_location_ignores_other_documents(self):
        self._create_document(self.vehicle, "STNK Disposal", "Wrong", is_bpkb=False)
        bidding = self.env["disposal.bidding"].create({"vehicle_id": self.vehicle.id})
        self.assertFalse(bidding.disposal_bpkb_location)

    def test_compute_refreshes_bpkb_location_without_an_asset(self):
        document = self._create_document(self.vehicle, "BPKB Refresh", "Solo", is_bpkb=True, is_license_plate=False)
        bidding = self.env["disposal.bidding"].create({"vehicle_id": self.vehicle.id})
        self.env.flush_all()
        document.bpkb_location = "Bandung"
        self.assertEqual(bidding.disposal_bpkb_location, "Solo")

        bidding.action_compute_unit_information()
        self.assertEqual(bidding.disposal_bpkb_location, "Bandung")

    def test_compute_refreshes_bpkb_location_with_an_asset(self):
        self._create_asset("2020-01-01")
        document = self._create_document(self.vehicle, "BPKB Asset", "Solo", is_bpkb=True, is_license_plate=False)
        bidding = self.env["disposal.bidding"].create({"vehicle_id": self.vehicle.id})
        document.bpkb_location = "Bandung"

        bidding.action_compute_unit_information()
        self.assertEqual(bidding.disposal_bpkb_location, "Bandung")

    def test_asset_is_resolved_from_the_vehicle_asset_number(self):
        asset = self._create_asset("2020-01-01")
        self.assertEqual(self.bidding._get_vehicle_asset(), asset)

    def test_ambiguous_asset_is_refused_instead_of_guessed(self):
        self._create_asset("2020-01-01")
        self._create_asset("2020-01-01")

        with self.assertRaises(ValidationError):
            self.bidding._get_vehicle_asset()

    def test_asset_linked_by_foreign_key_wins_over_the_name(self):
        if "vehicle_id" not in self.env["account.asset"]._fields:
            raise unittest.SkipTest("account_asset_fleet is not installed")

        named = self._create_asset("2020-01-01")
        linked = self._create_asset("2020-01-01")
        linked.write({"name": "Unrelated asset name", "vehicle_id": self.vehicle.id})

        self.assertNotEqual(named, linked)
        self.assertEqual(self.bidding._get_vehicle_asset(), linked)

    def test_aging_is_counted_from_the_acquisition_date(self):
        today = fields.Date.context_today(self.bidding)
        asset = self._create_asset(today - relativedelta(years=2, months=5))
        self.assertEqual(self.bidding._get_asset_aging(asset), "29")

        asset.acquisition_date = today - relativedelta(months=7)
        self.assertEqual(self.bidding._get_asset_aging(asset), "7")

        # A month that has not been completed yet does not count.
        asset.acquisition_date = today - relativedelta(months=7) + relativedelta(days=1)
        self.assertEqual(self.bidding._get_asset_aging(asset), "6")

        asset.acquisition_date = today
        self.assertEqual(self.bidding._get_asset_aging(asset), "0")

    def test_compute_uses_the_pre_refinancing_entry_after_a_leaseback(self):
        if "x_pre_refinancing_move_id" not in self.env["account.asset"]._fields:
            raise unittest.SkipTest("x_account_asset_leaseback is not installed")

        asset = self._create_asset("2020-01-01")
        asset.validate()
        asset.depreciation_move_ids.filtered(lambda move: move.state == "draft")._post()
        asset.set_to_close_leaseback(
            ar_account=self.receivable_account,
            ar_amount=360705000,
            deferred_account=self.expense_account,
            date=fields.Date.from_string("2020-09-03"),
        )
        self.assertEqual(
            asset.x_pre_refinancing_move_id.date, fields.Date.from_string("2020-08-31")
        )

        self.bidding.action_compute_unit_information()

        # Values of the last normal depreciation (Aug 31), not of the leaseback.
        self.assertEqual(self.bidding.disposal_monthly_depreciation, 6950000)
        self.assertEqual(self.bidding.disposal_accum_depreciation, 55600000)
        self.assertEqual(self.bidding.disposal_book_value, 361400000)

    def test_deferred_profit_loss_has_its_own_button(self):
        self._create_asset("2020-01-01")
        partner = self.env["res.partner"].create({"name": "Bidder"})
        self.bidding.write({"bidding_line_ids": [(0, 0, {"partner_id": partner.id, "bidding_price": 450000000})]})

        # Compute Unit Information leaves the deferred amount alone ...
        self.bidding.action_compute_unit_information()
        self.assertEqual(self.bidding.disposal_sisa_laba_rugi_ditangguhkan, 0.0)

        # ... it is only filled by its own button: Highest Bid - Book Value.
        self.bidding.action_generate_sisa_laba_rugi()
        deferred = 450000000 - self.bidding.disposal_book_value
        self.assertEqual(self.bidding.disposal_sisa_laba_rugi_ditangguhkan, deferred)

        # PHD then reuses the stored value.
        self.bidding.action_generate_phd()
        expected = (
            self.bidding.disposal_book_value * (1 + self.bidding._PPN_RATE)
            + self.bidding.disposal_penalti_pelunasan
            - deferred
        )
        self.assertAlmostEqual(self.bidding.disposal_phd, expected, places=2)

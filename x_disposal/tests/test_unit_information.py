import unittest
from dateutil.relativedelta import relativedelta
from lxml import etree

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

        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "Disposal Unit Information QA"})
        vehicle_model = cls.env["fleet.vehicle.model"].create({"name": "Disposal Unit QA", "brand_id": brand.id})
        cls.vehicle = cls.env["fleet.vehicle"].create({
            "model_id": vehicle_model.id,
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
        # No Deferred Item was configured for this refinancing, so no residual.
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 0)

    def _create_leaseback_deferred(self, asset, residual=5000000):
        """Real FK path and posted recognition, not an assigned residual cache."""
        event = self.env["account.move"].create({
            "journal_id": self.journal.id,
            "date": "2026-01-01",
            "asset_id": asset.id,
            "asset_move_type": "disposal",
            "x_refinancing_type": "leaseback",
        })
        asset.write({
            "vehicle_id": self.vehicle.id, "state": "leaseback",
            "leaseback_deferred_pl_amount": residual + 2000000,
        })
        model = self.env["account.deferred.model"].create({
            "name": "Disposal Deferred QA", "deferred_type": "expense",
            "company_id": self.company.id,
            "deferred_account_id": self._find_account(("asset_current",)).id,
            "recognition_account_id": self.expense_account.id,
            "journal_id": self.journal.id, "method_number": 2,
        })
        entry = self.env["account.deferred.entry"].create({
            "name": "Disposal Leaseback Residual QA", "deferred_type": "expense",
            "model_id": model.id, "company_id": self.company.id,
            "date": "2026-01-01", "source_move_id": event.id,
            "original_value": residual + 1000000, "method_number": 2,
            "line_ids": [fields.Command.create({
                "date": "2026-01-01", "sequence": 1, "amount": 1000000,
            }), fields.Command.create({
                "date": "2026-02-01", "sequence": 2, "amount": residual,
            })],
        })
        first = entry.line_ids.sorted("sequence")[:1]
        first._ensure_move()
        first.move_id.with_context(skip_deferred_generation=True).action_post()
        self.assertEqual(asset.state, "leaseback")
        self.assertEqual(asset.x_refinancing_move_id, event)
        self.assertEqual(entry.residual_value, residual)
        return entry

    def _deferred_entry(self, asset):
        return self.env["account.deferred.entry"].search([
            ("source_move_id", "=", asset.x_refinancing_move_id.id),
        ], limit=1)

    def _financial_case(self, deferred=5000000, gross_bid=111000000, penalty=2000000):
        asset = self._create_asset("2026-01-01", original_value=80000000)
        self._create_leaseback_deferred(asset, residual=deferred)
        tax_group = self.env["account.tax.group"].create({
            "name": "Disposal PPN QA", "company_id": self.company.id,
            "country_id": self.company.account_fiscal_country_id.id,
        })
        tax = self.env["account.tax"].create({
            "name": "Disposal PPN 11% QA", "amount": 11, "type_tax_use": "sale",
            "company_id": self.company.id, "tax_group_id": tax_group.id,
        })
        partner = self.env["res.partner"].create({"name": "Disposal Bidder QA"})
        self.bidding.write({
            "bidding_line_ids": [(0, 0, {"partner_id": partner.id, "bidding_price": gross_bid})],
            "selling_target_tax_id": tax.id, "disposal_penalti_pelunasan": penalty,
        })
        self.bidding.action_compute_unit_information()
        return asset, tax

    def test_vehicle_sale_profit_loss_and_deferred_residual_are_separate(self):
        asset, _tax = self._financial_case()
        # Unit Information copies the residual, not original value or sale gain.
        self.assertEqual(self.bidding.disposal_sisa_laba_rugi_ditangguhkan, 0.0)
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 5000000)
        self.bidding.action_generate_sisa_laba_rugi()
        self.assertEqual(self.bidding.selling_target_exclude_ppn, 100000000)
        self.assertEqual(self.bidding.disposal_book_value, 80000000)
        self.assertEqual(self.bidding.disposal_sisa_laba_rugi_ditangguhkan, 20000000)
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, self._deferred_entry(asset).residual_value)
        self.assertNotEqual(self.bidding.disposal_leaseback_deferred_profit_loss, asset.leaseback_deferred_pl_amount)
        self.assertEqual(self.bidding.selling_target_profit_loss_amount, 23000000)
        self.assertAlmostEqual(self.bidding.selling_target_profit_loss_percentage, 28.75, places=8)
        self.bidding.action_generate_phd()
        self.assertAlmostEqual(self.bidding.disposal_phd, 85800000, places=2)

    def test_compute_selling_target_refreshes_both_gains_without_double_counting(self):
        asset, _tax = self._financial_case()
        self.bidding.write({
            "disposal_sisa_laba_rugi_ditangguhkan": 999999999,
            "disposal_leaseback_deferred_profit_loss": 999999999,
        })
        self.bidding.action_compute_profit_loss()
        self.assertEqual(self.bidding.disposal_sisa_laba_rugi_ditangguhkan, 20000000)
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 5000000)
        self.assertEqual(self.bidding.selling_target_profit_loss_amount, 23000000)
        self.bidding.disposal_sisa_laba_rugi_ditangguhkan = 999999999
        self._deferred_entry(asset).original_value = 5000000
        self.bidding.action_generate_phd()
        self.assertAlmostEqual(self.bidding.disposal_phd, 86800000, places=2)
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 4000000)

    def test_deferred_residual_is_copied_literally_without_asset_sign_conversion(self):
        asset, _tax = self._financial_case(deferred=3000000, gross_bid=77700000)
        asset.leaseback_deferred_pl_amount = -3000000
        self.bidding.action_compute_profit_loss()
        self.assertEqual(self.bidding.selling_target_exclude_ppn, 70000000)
        self.assertEqual(self.bidding.disposal_sisa_laba_rugi_ditangguhkan, -10000000)
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 3000000)
        self.assertEqual(self.bidding.selling_target_profit_loss_amount, -9000000)
        self.bidding.action_generate_phd()
        self.assertAlmostEqual(self.bidding.disposal_phd, 87800000, places=2)

    def test_deferred_generate_copies_residual_only_including_zero(self):
        asset, _tax = self._financial_case()
        self.bidding.action_generate_sisa_laba_rugi()
        before = self.bidding.read(['disposal_sisa_laba_rugi_ditangguhkan', 'disposal_phd', 'selling_target_profit_loss_amount'])
        for value in (1234567.89, 0):
            self._deferred_entry(asset).original_value = value + 1000000
            self.bidding.action_generate_deferred_profit_loss()
            self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, value)
            self.assertEqual(self.bidding.read(list(before[0])), before)

    def test_missing_asset_clears_deferred_instead_of_using_old_sale_gain(self):
        self.bidding.write({
            'disposal_sisa_laba_rugi_ditangguhkan': 1234567,
            'disposal_leaseback_deferred_profit_loss': 7654321,
        })
        self.bidding.action_generate_deferred_profit_loss()
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 0)
        self.assertEqual(self.bidding.disposal_sisa_laba_rugi_ditangguhkan, 1234567)
        self.bidding.action_compute_unit_information()
        self.assertEqual(self.bidding.disposal_phd, 0)

    def test_zero_book_value_does_not_fall_back_to_asset_book_value(self):
        self._financial_case()
        self.bidding.disposal_book_value = 0
        self.bidding.action_compute_profit_loss()
        self.assertEqual(self.bidding.disposal_sisa_laba_rugi_ditangguhkan, 100000000)
        self.assertEqual(self.bidding.selling_target_profit_loss_amount, 103000000)
        self.assertEqual(self.bidding.selling_target_profit_loss_percentage, 0)

    def test_generate_sale_gain_refreshes_net_tax_base_and_keeps_tax_validation(self):
        _asset, tax = self._financial_case()
        self.bidding.selling_target_exclude_ppn = 1
        self.bidding.action_generate_sisa_laba_rugi()
        self.assertEqual(self.bidding.disposal_sisa_laba_rugi_ditangguhkan, 20000000)
        tax.price_include_override = 'tax_included'
        self.bidding.action_generate_sisa_laba_rugi()
        self.assertEqual(self.bidding.disposal_sisa_laba_rugi_ditangguhkan, 20000000)
        self.bidding.selling_target_tax_id = False
        with self.assertRaisesRegex(ValidationError, 'select Taxes'):
            self.bidding.action_generate_sisa_laba_rugi()

    def test_approved_snapshots_and_accounting_are_not_rewritten_by_new_actions(self):
        asset, _tax = self._financial_case()
        self.bidding.action_compute_profit_loss()
        self.bidding.with_context(x_disposal_post_approval=True).state = 'approved'
        before = self.bidding.read(['disposal_sisa_laba_rugi_ditangguhkan', 'disposal_leaseback_deferred_profit_loss', 'disposal_phd'])
        moves_before = self.env['account.move'].search_count([])
        for action in (self.bidding.action_generate_sisa_laba_rugi,
                       self.bidding.action_generate_deferred_profit_loss,
                       self.bidding.action_generate_phd,
                       self.bidding.action_compute_profit_loss):
            with self.assertRaisesRegex(ValidationError, 'approved'):
                action()
        self.assertEqual(self.bidding.read(list(before[0])), before)
        self.assertEqual(self.env['account.move'].search_count([]), moves_before)
        self.assertEqual(asset.leaseback_deferred_pl_amount, 7000000)

    def test_choose_vehicle_fills_residual_in_form_before_save(self):
        asset = self._create_asset("2026-01-01")
        entry = self._create_leaseback_deferred(asset)
        moves_before = self.env["account.move"].search_count([])
        with Form(self.env["disposal.bidding"]) as form:
            form.vehicle_id = self.vehicle
            self.assertEqual(form.disposal_leaseback_deferred_profit_loss, entry.residual_value)
            form.start_date = "2026-11-01"
            form.end_date = "2026-11-30"
        self.assertEqual(form.record.disposal_leaseback_deferred_profit_loss, 5000000)
        self.assertEqual(self.env["account.move"].search_count([]), moves_before)

    def test_vehicle_switch_and_clear_refresh_without_compute(self):
        asset = self._create_asset("2026-01-01")
        self._create_leaseback_deferred(asset)
        other = self.vehicle.copy({"license_plate": "B 4567 QA", "asset_number": "OTHER-RESIDUAL"})
        with Form(self.env["disposal.bidding"]) as form:
            form.vehicle_id = self.vehicle
            self.assertEqual(form.disposal_leaseback_deferred_profit_loss, 5000000)
            form.vehicle_id = other
            self.assertEqual(form.disposal_leaseback_deferred_profit_loss, 0)
            form.vehicle_id = self.vehicle
            form.vehicle_id = self.env["fleet.vehicle"]
            self.assertEqual(form.disposal_leaseback_deferred_profit_loss, 0)
            form.vehicle_id = other
            form.start_date = "2026-11-01"
            form.end_date = "2026-11-30"
        form.record.vehicle_id = self.vehicle
        self.assertEqual(form.record.disposal_leaseback_deferred_profit_loss, 5000000)
        form.record.vehicle_id = other
        self.assertEqual(form.record.disposal_leaseback_deferred_profit_loss, 0)

    def test_api_multi_create_uses_each_vehicles_residual_not_supplied_amount(self):
        asset = self._create_asset("2026-01-01")
        self._create_leaseback_deferred(asset)
        other = self.vehicle.copy({"asset_number": "OTHER-API"})
        records = self.env["disposal.bidding"].create([
            {"vehicle_id": self.vehicle.id, "disposal_leaseback_deferred_profit_loss": 999},
            {"vehicle_id": other.id, "disposal_leaseback_deferred_profit_loss": 999},
        ])
        self.assertEqual(records.mapped("disposal_leaseback_deferred_profit_loss"), [5000000, 0])

    def test_only_leaseback_asset_for_same_vehicle_is_used(self):
        asset = self._create_asset("2026-01-01")
        self._create_leaseback_deferred(asset)
        other = self.vehicle.copy({"asset_number": "OTHER-SOURCE"})
        other_bidding = self.env["disposal.bidding"].create({"vehicle_id": other.id})
        self.assertEqual(other_bidding.disposal_leaseback_deferred_profit_loss, 0)
        # Same names/plate fallback are deliberately not used for residuals.
        asset.vehicle_id = False
        self.bidding.action_generate_deferred_profit_loss()
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 0)
        asset.write({"vehicle_id": self.vehicle.id, "state": "draft"})
        self.bidding.action_generate_deferred_profit_loss()
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 0)

    def test_latest_leaseback_asset_used_despite_newer_draft_asset(self):
        older = self._create_asset("2026-01-01")
        self._create_leaseback_deferred(older, residual=8000000)
        latest = self._create_asset("2026-02-01")
        latest_entry = self._create_leaseback_deferred(latest, residual=2000000)
        draft = self._create_asset("2026-03-01")
        draft.vehicle_id = self.vehicle
        self.bidding.action_generate_deferred_profit_loss()
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, latest_entry.residual_value)

    def test_only_exact_refinancing_entry_not_other_or_stale_deferred_link(self):
        asset = self._create_asset("2026-01-01")
        old_entry = self._create_leaseback_deferred(asset, residual=9000000)
        new_entry = self._create_leaseback_deferred(asset, residual=3000000)
        new_entry.source_move_id.date = "2026-02-01"
        asset.deferred_expense_id = old_entry
        self.bidding.action_generate_deferred_profit_loss()
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 3000000)
        new_entry.source_move_id.button_cancel()
        # Cancelled refinancing is no longer the asset's current event.
        self.bidding.action_generate_deferred_profit_loss()
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 9000000)

    def test_cancelled_deferred_ignored_and_same_move_residuals_summed(self):
        asset = self._create_asset("2026-01-01")
        entry = self._create_leaseback_deferred(asset, residual=5000000)
        extra = self.env["account.deferred.entry"].create({
            "name": "Second residual", "deferred_type": entry.deferred_type,
            "model_id": entry.model_id.id, "date": "2026-01-01",
            "original_value": 2000000, "source_move_id": entry.source_move_id.id,
        })
        self.bidding.action_generate_deferred_profit_loss()
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 7000000)
        extra.action_cancel()
        self.bidding.action_generate_deferred_profit_loss()
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 5000000)

    def test_missing_deferred_item_returns_zero_not_original_leaseback_amount(self):
        asset = self._create_asset("2026-01-01")
        entry = self._create_leaseback_deferred(asset)
        entry.source_move_id = False
        self.bidding.action_generate_deferred_profit_loss()
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 0)

    def test_no_refinancing_entry_does_not_fall_back_to_original_gain(self):
        asset = self._create_asset("2026-01-01")
        entry = self._create_leaseback_deferred(asset)
        entry.source_move_id.button_cancel()
        self.assertFalse(asset.x_refinancing_move_id)
        self.bidding.action_generate_deferred_profit_loss()
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 0)

    def test_vehicle_company_not_current_ui_company_controls_source(self):
        asset = self._create_asset("2026-01-01")
        self._create_leaseback_deferred(asset)
        other_company = self.env["res.company"].create({
            "name": "Disposal Residual Other Company", "currency_id": self.company.currency_id.id,
        })
        self.assertEqual(self.bidding.with_company(other_company)._get_deferred_profit_loss_value(), 5000000)
        self.vehicle.company_id = other_company
        self.bidding.action_generate_deferred_profit_loss()
        self.assertEqual(self.bidding.disposal_leaseback_deferred_profit_loss, 0)

    def test_vehicle_change_on_approved_bidding_remains_blocked(self):
        asset = self._create_asset("2026-01-01")
        self._create_leaseback_deferred(asset)
        self.bidding.with_context(x_disposal_post_approval=True).state = "approved"
        other = self.vehicle.copy({"asset_number": "OTHER-APPROVED"})
        with self.assertRaisesRegex(ValidationError, "approved"):
            self.bidding.vehicle_id = other

    def test_native_form_and_report_distinguish_sale_gain_from_asset_deferred(self):
        self._financial_case()
        self.bidding.action_compute_profit_loss()
        self.assertEqual(self.bidding._fields['disposal_sisa_laba_rugi_ditangguhkan'].string, 'Laba Rugi Penjualan Kendaraan')
        self.assertEqual(self.bidding._fields['disposal_leaseback_deferred_profit_loss'].string, 'Sisa Laba Rugi Ditangguhkan')
        arch = etree.fromstring(self.bidding.get_view(view_type='form')['arch'])
        self.assertTrue(arch.xpath("//field[@name='disposal_leaseback_deferred_profit_loss'][@readonly='1']"))
        self.assertTrue(arch.xpath("//button[@name='action_generate_deferred_profit_loss']"))
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            'x_disposal.report_disposal_bidding_document', self.bidding.ids)
        self.assertIn(b'Laba Rugi Penjualan Kendaraan', html)
        self.assertIn(b'Sisa Laba Rugi Ditangguhkan', html)
        self.assertIn(b'20,000,000', html)
        self.assertIn(b'5,000,000', html)

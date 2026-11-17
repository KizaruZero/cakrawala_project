from odoo import api, models


class AccountAsset(models.Model):
    _inherit = "account.asset"

    @api.model
    def _latest_vehicle_duration_asset(self, vehicle_id, company_id, exclude_ids=()):
        """Latest real asset, including archives, within the same company.

        Creation date (then ID) defines newest, not acquisition date or the last
        edit date. Normal read permissions apply; this is not a sudo lookup.
        """
        if not vehicle_id or not company_id:
            return self.browse()
        return self.with_context(active_test=False).search([
            ("vehicle_id", "=", vehicle_id),
            ("company_id", "=", company_id),
            ("state", "!=", "model"),
            ("parent_id", "=", False),
            ("id", "not in", list(exclude_ids)),
        ], order="create_date desc, id desc", limit=1)

    def _apply_previous_vehicle_duration(self):
        for asset in self:
            if (asset.state != "draft" or asset.parent_id or not asset.vehicle_id
                    or asset.depreciation_move_ids.filtered(lambda move: move.state == "posted")):
                continue
            previous = self._latest_vehicle_duration_asset(
                asset.vehicle_id.id, asset.company_id.id, asset._origin.ids)
            if previous and asset.method_number != previous.leaseback_remaining_duration:
                # Copy the stored remaining months exactly, including zero.
                # Never fall back to the original full depreciation duration.
                asset.method_number = previous.leaseback_remaining_duration
                # Same invalidation as native manual Duration edits: retain no
                # stale Draft board for a different duration. Posted history is
                # excluded above, and the previous asset is never modified.
                if asset.depreciation_move_ids:
                    asset.onchange_consistent_board()

    @api.onchange("vehicle_id")
    def _onchange_vehicle_duration_from_previous_asset(self):
        self._apply_previous_vehicle_duration()

    @api.onchange("model_id")
    def _onchange_model_id(self):
        result = super()._onchange_model_id()
        # Native model defaults must not replace the vehicle-specific duration
        # when a fleet model is selected after the vehicle.
        self.filtered(lambda asset: asset.model_id.x_is_fleet)._apply_previous_vehicle_duration()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for values in vals_list:
            values = dict(values)
            if ("method_number" not in values and "default_method_number" not in self.env.context
                    and values.get("state", self.env.context.get("default_state")) != "model"
                    and not values.get("parent_id", self.env.context.get("default_parent_id"))):
                previous = self._latest_vehicle_duration_asset(
                    values.get("vehicle_id", self.env.context.get("default_vehicle_id")),
                    values.get("company_id") or self.env.context.get("default_company_id") or self.env.company.id,
                )
                if previous:
                    values["method_number"] = previous.leaseback_remaining_duration
            prepared.append(values)
        # Keep the existing one-active-asset-per-vehicle validation untouched.
        return super().create(prepared)

    def write(self, values):
        changed = self.browse()
        if "vehicle_id" in values and "method_number" not in values:
            changed = self.filtered(lambda asset: asset.state == "draft"
                                    and asset.vehicle_id.id != values["vehicle_id"])
        result = super().write(values)
        changed._apply_previous_vehicle_duration()
        return result

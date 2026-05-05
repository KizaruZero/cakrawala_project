from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FleetSpk(models.Model):
    _inherit = "fleet.spk"

    def action_create_replacement_car(self):
        """Open or create replacement.car when Unit Breakdown is set on the SPK."""
        self.ensure_one()
        if not self.unit_breakdown:
            raise ValidationError(
                _("Enable Unit Breakdown on this SPK before creating a replacement car request.")
            )
        if not self.vehicle_id:
            raise ValidationError(_("The SPK must have a vehicle."))

        ReplacementCar = self.env["replacement.car"]
        existing = ReplacementCar.search([("spk_ids", "in", self.ids)], limit=1)
        if existing:
            return {
                "type": "ir.actions.act_window",
                "name": _("Replacement Car"),
                "res_model": "replacement.car",
                "view_mode": "form",
                "res_id": existing.id,
                "target": "current",
            }

        vehicle = self.vehicle_id
        company = vehicle.company_id or self.env.company
        pic = self.pic_client or self.customer_id.display_name or _("PIC")
        est_date = self.planning_date or self.spk_date or fields.Date.context_today(self)

        replacement_car = ReplacementCar.create({
            "company_id": company.id,
            "vehicle_old_id": vehicle.id,
            "spk_ids": [(6, 0, [self.id])],
            "request_date": fields.Date.context_today(self),
            "pic_name": pic,
            "estimation_use_date": est_date,
            "reason": self.description or "",
        })
        self.message_post(
            body=_("Replacement car request created: %s") % replacement_car.display_name,
            message_type="notification",
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Replacement Car"),
            "res_model": "replacement.car",
            "view_mode": "form",
            "res_id": replacement_car.id,
            "target": "current",
        }

from odoo import _, api, fields, models
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
            "customer_id": self.customer_id.id if hasattr(self, 'customer_id') else False,
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

    def action_create_rc(self):
        """Override to return the correct default values for replacement.car fields."""
        self.ensure_one()
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

        pic = self.pic_client or self.customer_id.display_name or _("PIC")
        est_date = self.planning_date or self.spk_date or fields.Date.context_today(self)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Replacement Car'),
            'res_model': 'replacement.car',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_vehicle_old_id': self.vehicle_id.id,
                'default_spk_ids': [(6, 0, [self.id])],
                'default_customer_id': self.customer_id.id if hasattr(self, 'customer_id') else False,
                'default_pic_name': pic,
                'default_estimation_use_date': est_date,
                'default_reason': self.description or "",
            }
        }

    def _link_to_active_replacement_car(self):
        """Automatically links the SPK to the most recent replacement car of the same vehicle."""
        ReplacementCar = self.env['replacement.car']
        for spk in self:
            if not spk.vehicle_id:
                continue
            # Find the most recent replacement car for this vehicle (whether active or done)
            rc = ReplacementCar.search([
                ('vehicle_old_id', '=', spk.vehicle_id.id)
            ], order='id desc', limit=1)
            if rc and spk.id not in rc.spk_ids.ids:
                rc.write({'spk_ids': [(4, spk.id)]})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._link_to_active_replacement_car()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'vehicle_id' in vals or 'state' in vals:
            self._link_to_active_replacement_car()
        return res

    def action_open_spk(self):
        """Open the SPK record in form view inside the same tab."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('x_spk.fleet_spk_action')
        action['views'] = [(self.env.ref('x_spk.fleet_spk_form').id, 'form')]
        action['res_id'] = self.id
        action['target'] = 'current'
        return action



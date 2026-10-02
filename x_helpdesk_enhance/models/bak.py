from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Bak(models.Model):
    _inherit = "bak"

    helpdesk_ticket_id = fields.Many2one(
        "helpdesk.ticket",
        string="Helpdesk Ticket",
        ondelete="set null",
        copy=False,
    )
    replacement_car_ids = fields.One2many(
        'replacement.car',
        'bak_id',
        string="Replacement Cars",
    )
    replacement_car_count = fields.Integer(
        string="Replacement Car Count",
        compute="_compute_replacement_car_count",
    )
    has_helpdesk_rc = fields.Boolean(
        string="Has Helpdesk RC",
        compute="_compute_has_helpdesk_rc",
    )

    @api.depends('replacement_car_ids')
    def _compute_replacement_car_count(self):
        for rec in self:
            rec.replacement_car_count = len(rec.replacement_car_ids)

    @api.depends('helpdesk_ticket_id', 'helpdesk_ticket_id.replacement_car_ids')
    def _compute_has_helpdesk_rc(self):
        for rec in self:
            rec.has_helpdesk_rc = bool(
                rec.helpdesk_ticket_id and rec.helpdesk_ticket_id.replacement_car_ids
            )

    @api.onchange('vehicle_id')
    def _onchange_vehicle(self):
        super()._onchange_vehicle()
        if self.helpdesk_ticket_id:
            if self.helpdesk_ticket_id.partner_id:
                self.partner_id = self.helpdesk_ticket_id.partner_id
            if self.helpdesk_ticket_id.odometer:
                self.last_odometer = self.helpdesk_ticket_id.odometer

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_helpdesk_ticket_reference()
        return records

    def _sync_helpdesk_ticket_reference(self, previous_tickets=None):
        previous_tickets = previous_tickets or {}
        for record in self:
            previous_ticket = previous_tickets.get(record.id)
            current_ticket = record.helpdesk_ticket_id

            if previous_ticket and previous_ticket != current_ticket and previous_ticket.bak_reference_id == record:
                previous_ticket.write({"bak_reference_id": False})

            if current_ticket:
                current_ticket.write({"bak_reference_id": record.id})

    def write(self, vals):
        previous_tickets = {}
        if "helpdesk_ticket_id" in vals:
            previous_tickets = {record.id: record.helpdesk_ticket_id for record in self}

        result = super().write(vals)

        if "helpdesk_ticket_id" in vals:
            self._sync_helpdesk_ticket_reference(previous_tickets)

        return result

    def action_create_spk(self):
        self.ensure_one()
        action = super().action_create_spk()
        context = dict(action.get("context", {}))
        context["default_helpdesk_ticket_id"] = self.helpdesk_ticket_id.id
        action["context"] = context
        return action

    def action_view_replacement_car(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "name": "Replacement Car",
            "res_model": "replacement.car",
            "target": "current",
        }
        if len(self.replacement_car_ids) == 1:
            action["view_mode"] = "form"
            action["res_id"] = self.replacement_car_ids.id
        else:
            action["view_mode"] = "list,form"
            action["domain"] = [("id", "in", self.replacement_car_ids.ids)]
        return action

    def action_create_rc(self):
        self.ensure_one()
        if self.state not in ('confirm', 'done'):
            raise ValidationError("Replacement Car hanya dapat dibuat jika BAK sudah diapprove (Confirmed / Done).")
        if self.has_helpdesk_rc:
            raise ValidationError("Replacement Car sudah dibuat dari Helpdesk Ticket terkait.")
        if self.replacement_car_ids:
            return self.action_view_replacement_car()

        ReplacementCar = self.env["replacement.car"]
        rc = ReplacementCar.create({
            "bak_id": self.id,
            "helpdesk_ticket_id": self.helpdesk_ticket_id.id if self.helpdesk_ticket_id else False,
            "customer_id": self.partner_id.id if self.partner_id else False,
            "vehicle_old_id": self.vehicle_id.id,
            "request_date": fields.Date.context_today(self),
            "estimation_use_date": fields.Date.context_today(self),
            "pic_name": self.pic_client_name or (self.partner_id.name if self.partner_id else "PIC"),
            "reason": getattr(self, "chronology", False) or self.notes or self.name,
        })
        return {
            "type": "ir.actions.act_window",
            "name": "Replacement Car",
            "res_model": "replacement.car",
            "view_mode": "form",
            "res_id": rc.id,
            "target": "current",
        }
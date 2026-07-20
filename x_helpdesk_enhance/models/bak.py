from odoo import api, fields, models


class Bak(models.Model):
    _inherit = "bak"

    helpdesk_ticket_id = fields.Many2one(
        "helpdesk.ticket",
        string="Helpdesk Ticket",
        ondelete="set null",
        copy=False,
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
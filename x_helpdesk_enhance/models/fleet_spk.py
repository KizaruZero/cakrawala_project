from odoo import api, fields, models


class FleetSPK(models.Model):
    _inherit = "fleet.spk"

    helpdesk_ticket_id = fields.Many2one(
        "helpdesk.ticket",
        string="Helpdesk Ticket",
        ondelete="set null",
        copy=False,
    )
    unit_location = fields.Char(string="Lokasi Unit")

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        super()._onchange_vehicle_id()
        for record in self:
            if record.helpdesk_ticket_id:
                if record.helpdesk_ticket_id.odometer:
                    record.odometer = record.helpdesk_ticket_id.odometer
                if record.helpdesk_ticket_id.partner_id:
                    record.customer_id = record.helpdesk_ticket_id.partner_id.id
                if record.helpdesk_ticket_id.pic_client_name:
                    record.pic_client = record.helpdesk_ticket_id.pic_client_name
                if record.helpdesk_ticket_id.pic_client_phone:
                    record.pic_client_phone = record.helpdesk_ticket_id.pic_client_phone
                if record.helpdesk_ticket_id.unit_location:
                    record.unit_location = record.helpdesk_ticket_id.unit_location

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

            if previous_ticket and previous_ticket != current_ticket and previous_ticket.spk_reference_id == record:
                previous_ticket.write({"spk_reference_id": False})

            if current_ticket:
                current_ticket.write({"spk_reference_id": record.id})

    def write(self, vals):
        previous_tickets = {}
        if "helpdesk_ticket_id" in vals:
            previous_tickets = {record.id: record.helpdesk_ticket_id for record in self}

        result = super().write(vals)

        if "helpdesk_ticket_id" in vals:
            self._sync_helpdesk_ticket_reference(previous_tickets)

        return result
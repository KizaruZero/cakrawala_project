from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FleetSPK(models.Model):
    _inherit = "fleet.spk"

    helpdesk_ticket_id = fields.Many2one(
        "helpdesk.ticket",
        string="Helpdesk Ticket",
        ondelete="set null",
        copy=False,
        tracking=True,
    )
    unit_location = fields.Char(string="Lokasi Unit", tracking=True)
    has_helpdesk_rc = fields.Boolean(
        string="Has Helpdesk RC",
        compute="_compute_has_helpdesk_rc",
    )

    @api.depends(
        'helpdesk_ticket_id',
        'helpdesk_ticket_id.replacement_car_ids',
        'bak_reference_id',
        'bak_reference_id.replacement_car_ids',
    )
    def _compute_has_helpdesk_rc(self):
        for rec in self:
            rec.has_helpdesk_rc = bool(
                (rec.helpdesk_ticket_id and rec.helpdesk_ticket_id.replacement_car_ids) or
                (rec.bak_reference_id and rec.bak_reference_id.replacement_car_ids)
            )

    @api.depends(
        'replacement_car_ids',
        'helpdesk_ticket_id.replacement_car_ids',
        'bak_reference_id.replacement_car_ids',
    )
    def _compute_replacement_car_count(self):
        for spk in self:
            rcs = spk.replacement_car_ids
            if spk.helpdesk_ticket_id:
                rcs |= spk.helpdesk_ticket_id.replacement_car_ids
            if spk.bak_reference_id:
                rcs |= spk.bak_reference_id.replacement_car_ids
            spk.replacement_car_count = len(rcs)

    def action_view_replacement_car(self):
        self.ensure_one()
        rcs = self.replacement_car_ids
        if self.helpdesk_ticket_id:
            rcs |= self.helpdesk_ticket_id.replacement_car_ids
        if self.bak_reference_id:
            rcs |= self.bak_reference_id.replacement_car_ids
        action = {
            "type": "ir.actions.act_window",
            "name": _("Replacement Car"),
            "res_model": "replacement.car",
            "target": "current",
        }
        if len(rcs) == 1:
            action["view_mode"] = "form"
            action["res_id"] = rcs.id
        else:
            action["view_mode"] = "list,form"
            action["domain"] = [("id", "in", rcs.ids)]
        return action

    def action_create_replacement_car(self):
        if self.has_helpdesk_rc:
            raise ValidationError("Replacement Car sudah dibuat dari Helpdesk Ticket terkait.")
        res = super().action_create_replacement_car()
        ticket = self.helpdesk_ticket_id or (self.bak_reference_id.helpdesk_ticket_id if self.bak_reference_id else False)
        bak = self.bak_reference_id or (self.helpdesk_ticket_id.bak_reference_id if self.helpdesk_ticket_id else False)
        rc_id = res.get('res_id') if isinstance(res, dict) else False
        if rc_id:
            rc = self.env['replacement.car'].browse(rc_id)
            vals = {}
            if ticket and not rc.helpdesk_ticket_id:
                vals['helpdesk_ticket_id'] = ticket.id
            if bak and not rc.bak_id:
                vals['bak_id'] = bak.id
            if vals:
                rc.with_context(skip_rc_sync=True).write(vals)
        return res

    def _apply_helpdesk_ticket_info(self):
        for record in self:
            if record.helpdesk_ticket_id and record.helpdesk_ticket_id.exists():
                ticket = record.helpdesk_ticket_id
                if ticket.ticket_category_id and ticket.ticket_category_id.is_rc:
                    record.unit_breakdown = True
                if ticket.odometer:
                    record.odometer = ticket.odometer
                if ticket.partner_id:
                    record.customer_id = ticket.partner_id.id
                if ticket.pic_client_name:
                    record.pic_client = ticket.pic_client_name
                if ticket.pic_client_phone:
                    record.pic_client_phone = ticket.pic_client_phone
                if ticket.unit_location:
                    record.unit_location = ticket.unit_location

    @api.onchange('bak_reference_id')
    def _onchange_bak_reference_id(self):
        for record in self:
            if record.bak_reference_id and not record.helpdesk_ticket_id and record.bak_reference_id.helpdesk_ticket_id:
                record.helpdesk_ticket_id = record.bak_reference_id.helpdesk_ticket_id

    @api.onchange('helpdesk_ticket_id')
    def _onchange_helpdesk_ticket_id(self):
        self._apply_helpdesk_ticket_info()

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        super()._onchange_vehicle_id()
        self._apply_helpdesk_ticket_info()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("helpdesk_ticket_id") and "unit_breakdown" not in vals:
                ticket = self.env["helpdesk.ticket"].browse(vals["helpdesk_ticket_id"])
                if ticket.exists() and ticket.ticket_category_id and ticket.ticket_category_id.is_rc:
                    vals["unit_breakdown"] = True
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
                if record.bak_reference_id and not current_ticket.bak_reference_id:
                    current_ticket.write({"bak_reference_id": record.bak_reference_id.id})

            # Link existing RCs from Ticket or BAK to this SPK
            rcs = self.env['replacement.car']
            if current_ticket:
                rcs |= current_ticket.replacement_car_ids
            if record.bak_reference_id:
                rcs |= record.bak_reference_id.replacement_car_ids

            for rc in rcs:
                rc_vals = {}
                if record not in rc.spk_ids:
                    rc_vals['spk_ids'] = [(4, record.id)]
                if record.bak_reference_id and not rc.bak_id:
                    rc_vals['bak_id'] = record.bak_reference_id.id
                if rc_vals:
                    rc.with_context(skip_rc_sync=True).write(rc_vals)

    def write(self, vals):
        previous_tickets = {}
        if "helpdesk_ticket_id" in vals:
            previous_tickets = {record.id: record.helpdesk_ticket_id for record in self}

        result = super().write(vals)

        if "helpdesk_ticket_id" in vals or "bak_reference_id" in vals:
            self._sync_helpdesk_ticket_reference(previous_tickets)

        return result
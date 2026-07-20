from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    ticket_category_id = fields.Many2one(
        "helpdesk.ticket.category",
        string="Kategori Keluhan",
        tracking=True,
        ondelete="restrict",
    )
    ticketing_category_id = fields.Many2one(
        "helpdesk.ticketing.category",
        string="Ticketing Category",
        tracking=True,
        ondelete="restrict",
    )
    bak_reference_id = fields.Many2one(
        "bak",
        string="BAK Reference",
        readonly=True,
        copy=False,
        ondelete="set null",
    )
    spk_reference_id = fields.Many2one(
        "fleet.spk",
        string="SPK Reference",
        readonly=True,
        copy=False,
        ondelete="set null",
    )
    ticket_category_is_accident = fields.Boolean(
        related="ticket_category_id.is_accident",
        store=True,
        readonly=True,
    )

    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    vehicle_vin_sn = fields.Char(
        string="Serial Number (VIN)",
        compute="_compute_vehicle_info",
        readonly=True,
        store=False,
    )
    vehicle_license_plate = fields.Char(
        string="License Plate",
        compute="_compute_vehicle_info",
        readonly=True,
        store=False,
    )
    vehicle_color = fields.Char(
        string="Color",
        compute="_compute_vehicle_info",
        readonly=True,
        store=False,
    )
    vehicle_year = fields.Char(
        string="Year",
        compute="_compute_vehicle_info",
        readonly=True,
        store=False,
    )

    is_in_progress = fields.Boolean(
        string="Is In Progress",
        compute="_compute_is_in_progress",
        store=True,
        help="Computed helper to indicate ticket is in an 'in progress' stage (used by views).",
    )

    pic_id = fields.Many2one("res.partner", string="PIC")
    phone = fields.Char(string="No Telpon")
    unit_location = fields.Char(string="Lokasi Unit")
    odometer = fields.Float(string="Odometer")
    can_create_bak_or_spk = fields.Boolean(
        related="stage_id.can_create_bak_or_spk",
        string="Can Create BAK/SPK",
    )

    @api.depends('vehicle_id')
    def _compute_vehicle_info(self):
        for rec in self:
            v = rec.vehicle_id
            rec.vehicle_license_plate = v.fleet_document_license_plate if v else False
            rec.vehicle_color = v.color if v else False
            rec.vehicle_year = v.model_year if v else False
            rec.vehicle_vin_sn = v.fleet_document_vin_number if v else False

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id_odometer(self):
        for rec in self:
            if rec.vehicle_id:
                rec.odometer = rec.vehicle_id.odometer

    def _generate_ticket_ref_from_team(self):
        for ticket in self:
            team = ticket.team_id
            if not team or not team.ticket_code:
                continue
            team._ensure_ticket_sequence()
            if team.ticket_sequence_id:
                ticket.ticket_ref = team.ticket_sequence_id.sudo().next_by_id()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._generate_ticket_ref_from_team()
        return records

    @api.depends('stage_id')
    def _compute_is_in_progress(self):
        in_progress_names = {
            'in progress',
            'in_progress',
            'inprogress',
            'on progress',
            'on_progress',
            'progress',
            'proses',
            'dalam proses',
            'ongoing',
        }
        for rec in self:
            rec.is_in_progress = False
            if rec.stage_id and rec.stage_id.name:
                try:
                    name = rec.stage_id.name.strip().lower()
                except Exception:
                    name = ''
                if name in in_progress_names:
                    rec.is_in_progress = True

    def write(self, vals):
        if "ticket_category_id" in vals:
            for ticket in self:
                if (ticket.bak_reference_id or ticket.spk_reference_id) and vals["ticket_category_id"] != ticket.ticket_category_id.id:
                    raise ValidationError("Sub type tidak bisa diubah jika ticket sudah memiliki referensi BAK/SPK.")
        if "ticket_ref" in vals:
            for ticket in self:
                if ticket.bak_reference_id or ticket.spk_reference_id:
                    raise ValidationError("Ticket Number tidak bisa diubah jika BAK/SPK sudah terbuat.")
                    
        if "stage_id" in vals:
            new_stage = self.env["helpdesk.stage"].browse(vals["stage_id"])
            if new_stage.is_close_stage:
                if new_stage.close_user_ids:
                    if self.env.user not in new_stage.close_user_ids:
                        raise ValidationError("You are not authorized to close this ticket.")
                else:
                    if not self.env.user.has_group('base.group_system'):
                        raise ValidationError("You are not authorized to close this ticket.")
            
            for ticket in self:
                if ticket.stage_id and new_stage.id != ticket.stage_id.id:
                    min_seq = min(new_stage.sequence, ticket.stage_id.sequence)
                    max_seq = max(new_stage.sequence, ticket.stage_id.sequence)
                    intermediate_stages = self.env['helpdesk.stage'].search([
                        ('sequence', '>', min_seq),
                        ('sequence', '<', max_seq),
                        ('team_ids', 'in', ticket.team_id.id)
                    ])
                    if intermediate_stages:
                        raise ValidationError("Stage tidak bisa dilompatin, pergerakan stage harus berurutan.")
                        
        return super().write(vals)

    def action_create_bak(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("x_bak.action_bak")
        action["view_mode"] = "form"
        action["views"] = [(False, "form")]
        action["target"] = "current"
        action["context"] = {
            "default_partner_id": self.partner_id.id,
            "default_ticket_number": self.ticket_ref,
            "default_notes": self.name,
            "default_helpdesk_ticket_id": self.id,
            "default_vehicle_id": self.vehicle_id.id if self.vehicle_id else False,
            "default_phone": self.phone,
            "default_last_odometer": self.odometer,
        }
        return action

    def action_create_spk(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("x_spk.fleet_spk_action")

        maintenance_type_code = "repair"
        if self.ticket_category_is_accident:
            maintenance_type_code = "accident"

        maintenance_type = self.env["spk.maintenance.type"].search(
            [("code", "=", maintenance_type_code)],
            limit=1,
        )

        action["view_mode"] = "form"
        action["views"] = [(False, "form")]
        action["target"] = "current"
        action["context"] = {
            "default_customer_id": self.partner_id.id,
            "default_description": self.name,
            "default_category": "external",
            "default_maintenance_type_id": maintenance_type.id,
            "default_reference_ticket_number": self.ticket_ref,
            "default_helpdesk_ticket_id": self.id,
            "default_vehicle_id": self.vehicle_id.id if self.vehicle_id else False,
            "default_pic_client": self.pic_id.name if self.pic_id else False,
            "default_pic_client_phone": self.phone,
            "default_odometer": self.odometer,
            "default_unit_location": self.unit_location,
        }
        return action

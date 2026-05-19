from odoo import api, fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    ticket_category_id = fields.Many2one(
        "helpdesk.ticket.category",
        string="Detail Type",
        tracking=True,
        ondelete="restrict",
    )
    ticketing_category_id = fields.Many2one(
        "helpdesk.ticketing.category",
        string="Ticketing Category",
        tracking=True,
        ondelete="restrict",
    )
    ticket_category_is_accident = fields.Boolean(
        related="ticket_category_id.is_accident",
        store=True,
        readonly=True,
    )

    is_in_progress = fields.Boolean(
        string="Is In Progress",
        compute="_compute_is_in_progress",
        store=True,
        help="Computed helper to indicate ticket is in an 'in progress' stage (used by views).",
    )

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
        regenerate_ticket_ref = "team_id" in vals
        result = super().write(vals)
        if regenerate_ticket_ref:
            self._generate_ticket_ref_from_team()
        return result

    def action_regenerate_ticket_ref(self):
        self.ensure_one()
        self._generate_ticket_ref_from_team()
        return True

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
        }
        return action

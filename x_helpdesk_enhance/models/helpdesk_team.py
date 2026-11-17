from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError


class HelpdeskTeam(models.Model):
    _inherit = "helpdesk.team"

    ticket_code = fields.Char(
        string="Team Ticket Code",
        copy=False,
        tracking=True,
        help="Kode team untuk format nomor tiket, contoh: CC.",
    )
    ticket_sequence_id = fields.Many2one(
        "ir.sequence",
        string="Ticket Sequence",
        copy=False,
        ondelete="set null",
        help="Sequence untuk generate nomor ticket team ini.",
    )
    is_vehicle_mandatory = fields.Boolean(
        string="Mandatory Fleet (Vehicle)",
        help="If checked, vehicle field becomes mandatory for tickets in this team.",
    )
    stage_ticket_counts = fields.Json(
        string="Tickets per Stage",
        compute="_compute_stage_ticket_counts",
        help="Overview: the stages of the team in their order, with the number of its tickets in each.",
    )
    # The native default is bound to helpdesk's own function: rebind it to add Completed.
    stage_ids = fields.Many2many(default=lambda self: self._default_stage_ids())

    def _default_stage_ids(self):
        stages = super()._default_stage_ids()
        completed = self.env["helpdesk.stage"].search([("is_completed", "=", True)], limit=1)
        if completed:
            stages = [Command.set(stages[0][2] + [completed.id])]
        return stages

    def _compute_stage_ticket_counts(self):
        counts = {
            (team.id, stage.id): count
            for team, stage, count in self.env["helpdesk.ticket"]._read_group(
                [("team_id", "in", self.ids)], ["team_id", "stage_id"], ["__count"],
            )
        }
        for team in self:
            team.stage_ticket_counts = [
                {"id": stage.id, "name": stage.name, "count": counts.get((team.id, stage.id), 0)}
                for stage in team.stage_ids.sorted(lambda s: (s.sequence, s.id))
            ]

    def action_view_stage_tickets(self, stage_id):
        """Overview: the tickets of this team in one stage, whatever their date."""
        self.ensure_one()
        stage = self.env["helpdesk.stage"].browse(stage_id).exists()
        action = self.action_view_ticket()
        params = self._get_action_view_ticket_params()
        context = dict(params["context"], search_default_is_open=False)
        action.update(
            display_name=f"{self.name} - {stage.name}" if stage else self.name,
            domain=[("team_id", "=", self.id), ("stage_id", "=", stage.id)],
            context=context,
            view_mode=params["view_mode"],
            views=[(False, view) for view in params["view_mode"].split(",")],
        )
        return action

    _helpdesk_team_ticket_code_uniq = models.Constraint(
        "unique(ticket_code)",
        "Team Ticket Code harus unik.",
    )

    def _prepare_ticket_sequence_vals(self):
        self.ensure_one()
        return {
            "name": f"Helpdesk Ticket {self.name}",
            "code": f"x.helpdesk.ticket.team.{self.id}",
            "prefix": f"{self.ticket_code}/%(month)s/%(year)s/",
            "padding": 4,
            "number_next": 1,
            "number_increment": 1,
            "implementation": "no_gap",
            "company_id": self.company_id.id,
        }

    def _ensure_ticket_sequence(self):
        for team in self.filtered(lambda t: t.ticket_code and not t.ticket_sequence_id):
            sequence = self.env["ir.sequence"].sudo().create(team._prepare_ticket_sequence_vals())
            team.ticket_sequence_id = sequence.id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_ticket_sequence()
        return records

    def write(self, vals):
        if "ticket_code" in vals:
            for team in self:
                if team.ticket_code and vals["ticket_code"] != team.ticket_code:
                    raise ValidationError("Team Ticket Code hanya boleh diisi satu kali dan tidak bisa diubah.")
        result = super().write(vals)
        if "ticket_code" in vals:
            self._ensure_ticket_sequence()
        return result

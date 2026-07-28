from odoo import api, fields, models
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

    _sql_constraints = [
        (
            "helpdesk_team_ticket_code_uniq",
            "unique(ticket_code)",
            "Team Ticket Code harus unik.",
        )
    ]

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

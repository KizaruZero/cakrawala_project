from odoo import fields, models


class HelpdeskTicketCategory(models.Model):
    _name = "helpdesk.ticket.category"
    _description = "Helpdesk Ticket Category"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)
    is_accident = fields.Boolean(
        string="Accident Category",
        help="Centang jika kategori ini harus trigger pembuatan BAK.",
    )
    active = fields.Boolean(default=True)

    _helpdesk_ticket_category_name_uniq = models.Constraint(
        "unique(name)",
        "Nama category harus unik.",
    )

from odoo import fields, models


class HelpdeskTicketingCategory(models.Model):
    _name = "helpdesk.ticketing.category"
    _description = "Helpdesk Ticketing Category"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "helpdesk_ticketing_category_name_uniq",
            "unique(name)",
            "Nama ticketing category harus unik.",
        )
    ]

from odoo import fields, models


class ReplacementCar(models.Model):
    _inherit = 'replacement.car'

    helpdesk_ticket_id = fields.Many2one(
        'helpdesk.ticket',
        string="Helpdesk Ticket",
        copy=False,
        ondelete='set null',
    )
    bak_id = fields.Many2one(
        'bak',
        string="BAK Reference",
        copy=False,
        ondelete='set null',
    )

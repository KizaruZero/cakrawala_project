from odoo import fields, models


class ReplacementCar(models.Model):
    _inherit = 'replacement.car'

    crm_lead_id = fields.Many2one(
        'crm.lead',
        string='CRM Lead',
        ondelete='set null',
        copy=False,
    )

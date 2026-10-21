from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    purchase_fleet_terms = fields.Html(related='company_id.purchase_fleet_terms', readonly=False)

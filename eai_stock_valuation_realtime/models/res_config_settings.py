from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    eai_rt_claim_account_id = fields.Many2one(
        related='company_id.eai_rt_claim_account_id', readonly=False)
    eai_rt_price_diff_account_id = fields.Many2one(
        related='company_id.eai_rt_price_diff_account_id', readonly=False)
    eai_rt_inventory_diff_account_id = fields.Many2one(
        related='company_id.eai_rt_inventory_diff_account_id', readonly=False)
    eai_rt_scrap_account_id = fields.Many2one(
        related='company_id.eai_rt_scrap_account_id', readonly=False)
    eai_rt_auto_post = fields.Boolean(
        related='company_id.eai_rt_auto_post', readonly=False)

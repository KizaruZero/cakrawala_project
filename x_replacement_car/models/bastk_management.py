from odoo import api, fields, models


class BastkManagementRC(models.Model):
    """Extend bastk.management to track the Replacement Car that originated it."""
    _inherit = 'bastk.management'

    replacement_car_id = fields.Many2one(
        'replacement.car',
        string='RC Reference',
        ondelete='set null',
        readonly=True,
        copy=False,
        tracking=True,
    )

    def action_submit_outside(self):
        res = super().action_submit_outside()
        for rec in self:
            if rec.replacement_car_id:
                rec.replacement_car_id._sync_state_from_bastk()
        return res

    def action_submit_inside(self):
        res = super().action_submit_inside()
        for rec in self:
            if rec.replacement_car_id:
                rec.replacement_car_id._sync_state_from_bastk()
        return res

    def action_done(self):
        res = super().action_done()
        for rec in self:
            if rec.replacement_car_id:
                rec.replacement_car_id._sync_state_from_bastk()
        return res

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals or 'replacement_car_id' in vals:
            for rec in self:
                if rec.replacement_car_id:
                    rec.replacement_car_id._sync_state_from_bastk()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.replacement_car_id:
                rec.replacement_car_id._sync_state_from_bastk()
        return records
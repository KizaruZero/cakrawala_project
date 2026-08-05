
from odoo import fields, models


class BastkManagementRC(models.Model):
    """Extend bastk.management to track the Replacement Car that originated it."""
    _inherit = 'bastk.management'

    replacement_car_id = fields.Many2one(
        'replacement.car',
        string='RC Reference',
        ondelete='set null',
        readonly=True,
        copy=False,
    )
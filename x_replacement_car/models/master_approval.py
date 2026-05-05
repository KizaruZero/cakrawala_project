from odoo import models, fields, api
from odoo.exceptions import ValidationError

class MasterApproval(models.Model):
    _name = 'master.approval'
    _description = 'Master Approval'
    _order = 'sequence, id'

    sequence = fields.Integer(
        string="Sequence"
    )

    approver_id = fields.Many2one(
        'res.users',
        string="Approver"
    )
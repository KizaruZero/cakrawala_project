from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ReplacementApproval(models.Model):
    _name = 'replacement.approval'
    _description = 'Replacement Approval'
    _order = 'sequence, id'

    sequence = fields.Integer(
        string="Sequence"
    )

    approver_id = fields.Many2one(
        'res.users',
        string="Approver"
    )
    
    replacement_car_id = fields.Many2one(
        'replacement.car',
        string="Replacement Car"
    )
    
    state = fields.Selection([
        ('waiting', 'Waiting for Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='waiting', tracking=True)
    
    approval_date = fields.Datetime(string="Approval Date")
    reject_date = fields.Datetime(string="Reject Date")
    notes = fields.Text(string="Notes")

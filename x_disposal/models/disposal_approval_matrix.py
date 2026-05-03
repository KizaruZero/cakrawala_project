from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DisposalApprovalMatrix(models.Model):
    _name = "disposal.approval.matrix"
    _description = "Disposal Approval Matrix Configuration"

    name = fields.Char(string="Name", default="Disposal Approval Matrix")
    active = fields.Boolean(string="Active", default=True)
    is_default = fields.Boolean(string="Is Default Rule", default=False)
    approval_line_ids = fields.One2many('disposal.approval.matrix.line', 'matrix_id', string='Approval Sequence')

    @api.constrains('approval_line_ids')
    def _check_has_approval_lines(self):
        for record in self:
            if not record.approval_line_ids:
                raise ValidationError('Approval matrix must have at least one approval line.')


class DisposalApprovalMatrixLine(models.Model):
    _name = 'disposal.approval.matrix.line'
    _description = 'Disposal Approval Matrix Line'
    _order = 'sequence asc'

    matrix_id = fields.Many2one('disposal.approval.matrix', string='Approval Matrix', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=1)
    starting_amount = fields.Float(string='Starting Amount', required=True, default=0)
    approver_id = fields.Many2one('res.users', string='Approver', required=True, ondelete='restrict')
    delegate_id = fields.Many2one('res.users', string='Delegate')
    delegate_valid_from = fields.Date(string='Delegate Valid From')
    delegate_valid_to = fields.Date(string='Delegate Valid To')
    active = fields.Boolean(string='Active', default=True)

    @api.constrains('delegate_valid_from', 'delegate_valid_to')
    def _check_delegate_date_validity(self):
        for record in self:
            if record.delegate_valid_from and record.delegate_valid_to:
                if record.delegate_valid_from > record.delegate_valid_to:
                    raise ValidationError('Delegate Valid From must be earlier than or equal to Delegate Valid To')

from odoo import models, fields
from odoo.exceptions import ValidationError


class DisposalApprovalActionWizard(models.TransientModel):
    _name = 'disposal.approval.action.wizard'
    _description = 'Disposal Approval Action Wizard'

    action_type = fields.Selection([('approve', 'Approve'), ('reject', 'Reject')], string='Action', required=True, default='approve')
    bidding_id = fields.Many2one('disposal.bidding', string='Bidding', required=True)
    approval_tracking_id = fields.Many2one('disposal.approval.tracking', string='Approval Record', required=True)
    remarks = fields.Text(string='Notes / Remarks')
    attachment_ids = fields.Many2many('ir.attachment', string='PDF Attachments')

    def action_confirm(self):
        self.ensure_one()

        invalid = self.attachment_ids.filtered(lambda a: a.mimetype and a.mimetype != 'application/pdf')
        if invalid:
            raise ValidationError('Only PDF files are allowed as attachments.')

        if self.approval_tracking_id.bidding_id != self.bidding_id:
            raise ValidationError('Selected approval record does not belong to this Bidding.')

        self.approval_tracking_id.sudo().write({
            'remarks': self.remarks,
            'attachment_ids': [(4, att.id) for att in self.attachment_ids],
        })

        if self.action_type == 'approve':
            self.approval_tracking_id.action_approve()
        else:
            self.approval_tracking_id.action_reject()

        return {'type': 'ir.actions.act_window_close'}

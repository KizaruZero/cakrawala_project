from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DisposalApprovalTracking(models.Model):
    _name = 'disposal.approval.tracking'
    _description = 'Disposal Approval Tracking'
    _order = 'sequence asc, id asc'

    bidding_id = fields.Many2one('disposal.bidding', string='Bidding', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=1)
    approver_id = fields.Many2one('res.users', string='Approver', required=True)
    delegate_id = fields.Many2one('res.users', string='Delegate')
    delegate_valid_from = fields.Date(string='Delegate Valid From')
    delegate_valid_to = fields.Date(string='Delegate Valid To')

    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='pending')

    date = fields.Datetime(string='Action Date')
    remarks = fields.Text(string='Remarks')
    attachment_ids = fields.Many2many('ir.attachment', 'disposal_approval_tracking_attachment_rel', 'tracking_id', 'attachment_id', string='Attachments')

    def _is_delegate_valid(self, today=None):
        self.ensure_one()
        if not self.delegate_id:
            return False
        if today is None:
            today = fields.Date.context_today(self)
        if self.delegate_valid_from and today < self.delegate_valid_from:
            return False
        if self.delegate_valid_to and today > self.delegate_valid_to:
            return False
        return True

    def _check_actor(self):
        self.ensure_one()
        current_user = self.env.user
        today = fields.Date.context_today(self)

        if current_user == self.approver_id:
            return
        if self.delegate_id and current_user == self.delegate_id and self._is_delegate_valid(today):
            return

        raise ValidationError('You are not authorized to act on this approval. Only the assigned approver or a valid delegate can approve/reject.')

    def action_approve(self):
        self.ensure_one()
        self._check_actor()

        if self.state != 'pending':
            raise ValidationError('This approval record is no longer pending.')

        bidding = self.bidding_id
        first_pending = bidding.approval_tracking_ids.filtered(lambda t: t.state == 'pending').sorted(key=lambda t: (t.sequence, t.id))[:1]
        if first_pending and first_pending != self:
            raise ValidationError('Approval must follow sequence order. Current approver is: %s' % first_pending.approver_id.display_name)

        self.write({'state': 'approved', 'date': fields.Datetime.now()})

        remaining = bidding.approval_tracking_ids.filtered(lambda t: t.state == 'pending')
        if not remaining:
            bidding.state = 'approved'
            bidding.message_post(body='Bidding has been fully approved.')
            bidding._post_approval_actions()
        else:
            bidding._send_next_approver_notification(is_reminder=False)

    def action_reject(self):
        self.ensure_one()
        self._check_actor()

        if self.state != 'pending':
            raise ValidationError('This approval record is no longer pending.')

        self.write({'state': 'rejected', 'date': fields.Datetime.now()})

        remaining = self.bidding_id.approval_tracking_ids.filtered(lambda t: t.state == 'pending' and t.id != self.id)
        if remaining:
            remaining.write({'state': 'cancelled', 'date': fields.Datetime.now()})

        self.bidding_id.state = 'rejected'
        self.bidding_id.message_post(body='Bidding has been rejected by %s.' % self.env.user.display_name)

    def write(self, vals):
        if self.env.context.get('allow_reset_to_draft'):
            return super(DisposalApprovalTracking, self).write(vals)
        for rec in self:
            if rec.state in ('approved', 'rejected', 'cancelled'):
                # Prevent edits after action is completed
                raise ValidationError('This approval record cannot be modified after action completed.')
        return super(DisposalApprovalTracking, self).write(vals)

    def unlink(self):
        if self.env.context.get('allow_reset_to_draft'):
            return super(DisposalApprovalTracking, self).unlink()
        for rec in self:
            if rec.state != 'pending':
                raise ValidationError('Cannot delete approval records that have been processed.')
        return super(DisposalApprovalTracking, self).unlink()

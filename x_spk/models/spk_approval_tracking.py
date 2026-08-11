from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class SpkApprovalTracking(models.Model):
    _name = 'spk.approval.tracking'
    _description = 'SPK Approval Tracking'
    _order = 'sequence asc, id asc'

    spk_id = fields.Many2one(
        'fleet.spk',
        string='SPK',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(string='Sequence', default=1)
    approver_id = fields.Many2one(
        'res.users',
        string='Approver',
        required=True,
    )
    delegate_id = fields.Many2one(
        'res.users',
        string='Delegate',
    )
    delegate_valid_from = fields.Date(string='Delegate Valid From')
    delegate_valid_to = fields.Date(string='Delegate Valid To')

    state = fields.Selection([
        ('pending', 'Waiting Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='pending')

    date = fields.Datetime(string='Action Date')
    remarks = fields.Text(string='Remarks')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'spk_approval_tracking_attachment_rel',
        'tracking_id',
        'attachment_id',
        string='Attachments',
    )

    def unlink(self):
        """Only untouched ('pending') approval steps may be removed.

        Once an approver acted on the step it belongs to the SPK audit trail and is kept.
        There is no archive counterpart here on purpose: these are cascade children of
        fleet.spk with no stand-alone view, and hiding them would break the approval
        history shown on the SPK form. Deleting the parent SPK — only possible while it is
        still New — still cascades at database level.
        """
        processed = self.filtered(lambda tracking: tracking.state != 'pending')
        if processed:
            raise UserError(_(
                "Approval steps that were already approved, rejected or cancelled "
                "cannot be deleted — they are part of the SPK approval history."
            ))
        return super().unlink()

    def _is_delegate_valid(self, today=None):
        """Check whether the delegate's validity period covers today."""
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
        """
        Raise ValidationError if the current user is not authorized to act
        on this approval record (must be approver or valid delegate).
        """
        self.ensure_one()
        current_user = self.env.user
        today = fields.Date.context_today(self)

        if current_user == self.approver_id:
            return
        if self.delegate_id and current_user == self.delegate_id and self._is_delegate_valid(today):
            return

        raise ValidationError(
            "You are not authorized to act on this approval. "
            "Only the assigned approver or a valid delegate can approve/reject."
        )

    def action_approve(self):
        """
        Mark this tracking record as approved.
        If no more pending records remain → set SPK state to 'approved'
        and trigger post-approval actions.
        """
        self.ensure_one()
        self._check_actor()

        if self.state != 'pending':
            raise ValidationError("This approval record is no longer pending.")

        spk = self.spk_id
        first_pending = spk.approval_tracking_ids.filtered(
            lambda t: t.state == 'pending'
        ).sorted(key=lambda t: (t.sequence, t.id))[:1]

        if first_pending and first_pending != self:
            raise ValidationError(
                "Approval must follow sequence order. "
                "Current approver is: %s" % first_pending.approver_id.display_name
            )

        self.write({
            'state': 'approved',
            'date': fields.Datetime.now(),
        })

        remaining_pending = spk.approval_tracking_ids.filtered(lambda t: t.state == 'pending')
        if not remaining_pending:
            spk.state = 'approved'
            spk.message_post(body="SPK has been fully approved.")
            spk._post_approval_actions()
        else:
            spk._send_next_approver_notification(is_reminder=False)

    def action_reject(self):
        """
        Mark this tracking record as rejected.
        Cancel all remaining pending approvals and set SPK to 'rejected'.
        """
        self.ensure_one()
        self._check_actor()

        if self.state != 'pending':
            raise ValidationError("This approval record is no longer pending.")

        self.write({
            'state': 'rejected',
            'date': fields.Datetime.now(),
        })

        remaining = self.spk_id.approval_tracking_ids.filtered(
            lambda t: t.state == 'pending' and t.id != self.id
        )
        if remaining:
            remaining.write({
                'state': 'cancelled',
                'date': fields.Datetime.now(),
            })

        self.spk_id.state = 'rejected'
        self.spk_id.message_post(
            body="SPK has been rejected by %s." % self.env.user.display_name
        )

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class SPKApprovalLine(models.Model):
    _name = "spk.approval.line"
    _description = "SPK Approval Line"
    _order = "sequence asc"

    spk_id = fields.Many2one(
        "fleet.spk",
        string="SPK",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="Sequence", default=1)
    approver_id = fields.Many2one(
        "res.users",
        string="Approver",
        required=True,
    )
    state = fields.Selection(
        [
            ("pending", "Waiting Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        string="Approval Status",
        default="pending",
    )
    action_date = fields.Datetime(string="Action Date")
    remarks = fields.Text(string="Remarks")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        string="Attachments",
    )
    approval_cycle = fields.Integer(
        string="Approval Cycle",
        default=1,
        required=True,
        readonly=True,
        help="Deprecated field - kept for backward compatibility"
    )
    can_current_user_delegate = fields.Boolean(
        string="Can Current User Delegate",
        compute="_compute_can_current_user_delegate",
    )

    approval_status = fields.Selection(
        related="state",
        string="Approval Status (Legacy)",
        store=True,
        readonly=True,
        help="Deprecated - use 'state' instead"
    )
    approval_date = fields.Datetime(
        related="action_date",
        string="Approval Date (Legacy)",
        store=True,
        readonly=True,
        help="Deprecated - use 'action_date' instead"
    )
    comments = fields.Text(
        related="remarks",
        string="Comments (Legacy)",
        readonly=True,
        help="Deprecated - use 'remarks' instead"
    )

    @api.depends("state", "approver_id")
    def _compute_can_current_user_delegate(self):
        current_user = self.env.user
        is_admin = current_user.has_group("base.group_system")
        for approval in self:
            approval.can_current_user_delegate = bool(
                approval.state == "pending"
                and (approval.approver_id == current_user or is_admin)
            )

    def _check_assigned_approver(self):
        for approval in self:
            if approval.approver_id != self.env.user and not self.env.su:
                raise ValidationError(
                    "Only assigned approver can process this approval stage."
                )

    def write(self, vals):
        protected_fields = {"state", "action_date", "approver_id", "remarks", "attachment_ids"}
        if (
            not self.env.su
            and not self.env.context.get("skip_approval_write_check")
            and protected_fields.intersection(vals.keys())
        ):
            self._check_assigned_approver()
        return super().write(vals)

    def unlink(self):
        """Same rule as spk.approval.tracking: a processed step is history."""
        processed = self.filtered(lambda approval: approval.state != "pending")
        if processed:
            raise UserError(_(
                "Approval lines that were already approved, rejected or cancelled "
                "cannot be deleted — they are part of the SPK approval history."
            ))
        return super().unlink()

    def _open_action_wizard(self, action_type):
        self.ensure_one()
        self._check_assigned_approver()
        return {
            "type": "ir.actions.act_window",
            "name": "SPK Approval Action",
            "res_model": "spk.approval.action.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_spk_id": self.spk_id.id,
                "default_approval_id": self.id,
                "default_action_type": action_type,
            },
        }

    def action_open_approve_wizard(self):
        self.ensure_one()
        return self._open_action_wizard("approve")

    def action_open_reject_wizard(self):
        self.ensure_one()
        return self._open_action_wizard("reject")

    def action_approve(self):
        for approval in self:
            request = approval.spk_id
            if not request:
                continue

            approval._check_assigned_approver()

            pending_approvals = request.approval_line_ids.filtered(
                lambda item: item.state == "pending"
            ).sorted(key=lambda item: (item.sequence, item.id))

            current_step = pending_approvals[:1]
            if current_step and current_step != approval:
                raise ValidationError(
                    "Approval must follow sequence order. "
                    "Current approver is: %s" % current_step.approver_id.display_name
                )

            approval.sudo().with_context(skip_approval_write_check=True).write({
                "state": "approved",
                "action_date": fields.Datetime.now(),
            })

            remaining_pending = request.approval_line_ids.filtered(
                lambda item: item.state == "pending"
            )
            if remaining_pending:
                request._send_next_approver_notification(is_reminder=False)
            else:
                request.state = "approved"
                request._post_approval_actions()

    def action_reject(self):
        for approval in self:
            request = approval.spk_id
            if not request:
                continue

            approval._check_assigned_approver()

            approval.sudo().with_context(skip_approval_write_check=True).write({
                "state": "rejected",
                "action_date": fields.Datetime.now(),
            })

            remaining = request.approval_line_ids.filtered(
                lambda item: item.state == "pending"
            )
            if remaining:
                remaining.sudo().with_context(skip_approval_write_check=True).write({
                    "state": "cancelled",
                    "action_date": fields.Datetime.now(),
                })

            request.state = "draft"

from odoo import models, fields, api
from odoo.exceptions import ValidationError


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
    role = fields.Selection(
        [
            ("l1", "Manager"),
            ("l2", "Senior Manager"),
            ("l3", "Director"),
        ],
        string="Role",
        required=True,
        default="l1",
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
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

    # Backward-compatible aliases (deprecated)
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
        protected_fields = {
            "state",
            "action_date",
            "approver_id",
            "role",
            "remarks",
            "attachment_ids",
        }
        if (
            not self.env.su
            and not self.env.context.get("skip_approval_write_check")
            and protected_fields.intersection(vals.keys())
        ):
            self._check_assigned_approver()
        return super().write(vals)

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
        role_order = {"l1": 1, "l2": 2, "l3": 3}
        for approval in self:
            request = approval.spk_id
            if not request:
                continue

            approval._check_assigned_approver()

            pending_approvals = request.approval_line_ids.filtered(
                lambda item: item.state == "pending"
            ).sorted(key=lambda item: (role_order.get(item.role, 99), item.sequence, item.id))
            current_step = pending_approvals[:1]
            if current_step and current_step != approval:
                raise ValidationError(
                    "Current approver stage is assigned to %s."
                    % current_step.approver_id.display_name
                )

            approval.sudo().with_context(skip_approval_write_check=True).write(
                {
                    "state": "approved",
                    "action_date": fields.Datetime.now(),
                }
            )

            remaining_pending = request.approval_line_ids.filtered(
                lambda item: item.state == "pending"
            )
            if remaining_pending:
                request.state = "waiting_approval"
                request._send_next_approver_notification(is_reminder=False)
            else:
                request.state = "approved"
                request._post_approval_actions()

    def action_reject(self):
        role_order = {"l1": 1, "l2": 2, "l3": 3}
        for approval in self:
            request = approval.spk_id
            if not request:
                continue

            approval._check_assigned_approver()

            approval.sudo().with_context(skip_approval_write_check=True).write(
                {
                    "state": "rejected",
                    "action_date": fields.Datetime.now(),
                }
            )

            current_rank = role_order.get(approval.role, 0)
            upper_pending = request.approval_line_ids.filtered(
                lambda item: item.state == "pending"
                and (
                    role_order.get(item.role, 0) > current_rank
                    or (
                        role_order.get(item.role, 0) == current_rank
                        and item.sequence > approval.sequence
                    )
                )
            )
            if upper_pending:
                upper_pending.sudo().with_context(skip_approval_write_check=True).write(
                    {
                        "state": "cancelled",
                        "action_date": fields.Datetime.now(),
                    }
                )

            request.state = "draft"

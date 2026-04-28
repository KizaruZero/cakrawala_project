from odoo import models, fields
from odoo.exceptions import ValidationError


class SPKApprovalActionWizard(models.TransientModel):
    _name = "spk.approval.action.wizard"
    _description = "SPK Approval Action Wizard"

    action_type = fields.Selection(
        [
            ("approve", "Approve"),
            ("reject", "Reject"),
        ],
        string="Action",
        required=True,
        default="approve",
    )
    spk_id = fields.Many2one("fleet.spk", string="SPK", required=True)
    approval_id = fields.Many2one("spk.approval.line", string="Approval Line", required=True)
    remarks = fields.Text(string="Notes / Remarks")
    attachment_ids = fields.Many2many("ir.attachment", string="PDF Attachments")

    def action_confirm(self):
        self.ensure_one()

        invalid_attachments = self.attachment_ids.filtered(
            lambda attachment: attachment.mimetype and attachment.mimetype != "application/pdf"
        )
        if invalid_attachments:
            raise ValidationError("Only PDF files are allowed as attachments.")

        if self.approval_id.spk_id != self.spk_id:
            raise ValidationError("Selected approval line does not belong to this SPK.")

        # Explicitly validate actor before sudo writes (ACL for normal users is read-only).
        self.approval_id._check_assigned_approver()

        self.approval_id.sudo().with_context(skip_approval_write_check=True).write(
            {
                "remarks": self.remarks,
                "attachment_ids": [(6, 0, self.attachment_ids.ids)],
            }
        )

        if self.action_type == "approve":
            self.approval_id.action_approve()
        else:
            self.approval_id.action_reject()

        return {"type": "ir.actions.act_window_close"}

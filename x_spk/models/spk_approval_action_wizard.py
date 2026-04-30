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
    # References spk.approval.tracking (execution layer — not the old spk.approval.line)
    approval_tracking_id = fields.Many2one(
        "spk.approval.tracking",
        string="Approval Record",
        required=True,
    )
    remarks = fields.Text(string="Notes / Remarks")
    attachment_ids = fields.Many2many("ir.attachment", string="PDF Attachments")

    def action_confirm(self):
        self.ensure_one()

        invalid_attachments = self.attachment_ids.filtered(
            lambda a: a.mimetype and a.mimetype != "application/pdf"
        )
        if invalid_attachments:
            raise ValidationError("Only PDF files are allowed as attachments.")

        if self.approval_tracking_id.spk_id != self.spk_id:
            raise ValidationError("Selected approval record does not belong to this SPK.")

        # Write remarks and attachments to the tracking record before acting
        self.approval_tracking_id.sudo().write({
            "remarks": self.remarks,
            "attachment_ids": [(4, att.id) for att in self.attachment_ids],
        })

        if self.action_type == "approve":
            self.approval_tracking_id.action_approve()
        else:
            self.approval_tracking_id.action_reject()

        return {"type": "ir.actions.act_window_close"}

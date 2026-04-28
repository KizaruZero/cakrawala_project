from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SPKApprovalMatrix(models.Model):
    _name = "spk.approval.matrix"
    _description = "SPK Approval Matrix Configuration"

    name = fields.Char(
        string="Name",
        required=True,
        compute="_compute_name",
        store=True,
        readonly=True,
        help="Auto-generated descriptive name\n[Default] format for default rules\n[Category - Amount Range - Type] for specific rules"
    )
    active = fields.Boolean(
        string="Active",
        default=True,
    )
    is_default = fields.Boolean(
        string="Is Default Rule",
        default=False,
        help="Mark this as the default approval rule. Used when no specific rule matches."
    )
    category = fields.Selection(
        [
            ("internal", "Internal"),
            ("external", "External"),
        ],
        string="Category",
        required=True,
    )
    maintenance_type_id = fields.Many2one(
        "spk.maintenance.type",
        string="Maintenance Type",
        required=True,
        ondelete="restrict",
        default=lambda self: self.env["spk.maintenance.type"].search(
            [("code", "=", "schedule")], limit=1
        ),
    )
    maintenance_type = fields.Char(
        string="Maintenance Type Code",
        related="maintenance_type_id.code",
        store=True,
        readonly=True,
    )
    amount_from = fields.Float(
        string="Amount From",
        required=True,
    )
    amount_to = fields.Float(
        string="Amount To",
        required=True,
    )
    approval_line_ids = fields.One2many(
        "spk.approval.matrix.line",
        "matrix_id",
        string="Approval Sequence",
    )

    _sql_constraints = [
        (
            "check_amount_range",
            "CHECK(amount_from <= amount_to)",
            "Amount From must be less than or equal to Amount To"
        ),
    ]

    @api.depends("is_default", "category", "maintenance_type_id", "amount_from", "amount_to")
    def _compute_name(self):
        """Auto-generate descriptive name for approval matrix"""
        def format_currency(amount):
            """Format amount as IDR currency"""
            return f"Rp {amount:,.0f}".replace(",", ".")

        for record in self:
            if record.is_default:
                category_label = dict(record._fields['category'].selection).get(record.category, record.category)
                record.name = f"{category_label} (Default)"
            else:
                category_label = dict(record._fields['category'].selection).get(record.category, record.category)
                amount_from = format_currency(record.amount_from)
                amount_to = format_currency(record.amount_to)
                mt_name = record.maintenance_type_id.name if record.maintenance_type_id else "N/A"
                record.name = f"{category_label} - {amount_from} s/d {amount_to} - {mt_name}"

    @api.constrains("is_default", "category", "active")
    def _check_single_default_per_category(self):
        """Ensure only one default active rule per category"""
        for record in self:
            if record.is_default and record.active:
                duplicates = self.search([
                    ("id", "!=", record.id),
                    ("category", "=", record.category),
                    ("is_default", "=", True),
                    ("active", "=", True),
                ])
                if duplicates:
                    raise ValidationError(
                        f"There is already a default approval rule for '{record.category}' category. "
                        "Only one active default rule allowed per category."
                    )


class SPKApprovalMatrixLine(models.Model):
    _name = "spk.approval.matrix.line"
    _description = "SPK Approval Matrix Line"
    _order = "sequence asc"

    matrix_id = fields.Many2one(
        "spk.approval.matrix",
        string="Approval Matrix",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=1,
    )
    approval_role_id = fields.Many2one(
        "res.groups.approval.role",
        string="Approval Role",
        required=True,
        ondelete="restrict",
        help="Select the approval role for this sequence level"
    )
    # Deprecated fields kept for backward compatibility
    approver_role = fields.Many2one(
        "res.groups",
        string="Approver Role (Deprecated)",
        readonly=True,
        help="Deprecated - use approval_role_id instead"
    )
    approval_role = fields.Selection(
        [
            ("l1", "Level 1 (Manager)"),
            ("l2", "Level 2 (Senior Manager)"),
            ("l3", "Level 3 (Director)"),
        ],
        string="Approval Role (Deprecated)",
        readonly=True,
        help="Deprecated - derived from approval_role_id.sequence"
    )
    is_final_approver = fields.Boolean(
        string="Final Approver (Deprecated)",
        default=False,
        readonly=True,
        help="Deprecated - kept for backward compatibility"
    )

    @api.onchange("approval_role_id")
    def _onchange_approval_role_id(self):
        """Auto-populate approval_role from the selected role's sequence for backward compatibility"""
        if self.approval_role_id:
            # Map sequence to approval_role levels (1=l1, 2=l2, 3=l3)
            sequence = self.approval_role_id.sequence
            if sequence == 1:
                self.approval_role = "l1"
            elif sequence == 2:
                self.approval_role = "l2"
            elif sequence >= 3:
                self.approval_role = "l3"

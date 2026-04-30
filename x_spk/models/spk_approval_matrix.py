from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SPKApprovalMatrix(models.Model):
    _name = "spk.approval.matrix"
    _description = "SPK Approval Matrix Configuration"

    name = fields.Char(
        string="Name",
        compute="_compute_name",
        store=True,
        readonly=True,
        help="Auto-generated: '[Category (Default)]' for default rules, '[Category - Type]' for specific rules."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
    )
    is_default = fields.Boolean(
        string="Is Default Rule",
        default=False,
        help="Mark as default. Used as fallback when no specific rule matches the SPK."
    )
    category = fields.Selection(
        [
            ("internal", "Internal"),
            ("external", "External"),
        ],
        string="Category",
        required=True,
    )
    # Not required for default rules — only mandatory for specific (non-default) matrices
    maintenance_type_id = fields.Many2one(
        "spk.maintenance.type",
        string="Maintenance Type",
        required=False,
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
    approval_line_ids = fields.One2many(
        "spk.approval.matrix.line",
        "matrix_id",
        string="Approval Sequence",
    )

    @api.depends("is_default", "category", "maintenance_type_id")
    def _compute_name(self):
        for record in self:
            category_label = dict(record._fields['category'].selection).get(record.category, record.category or "")
            if record.is_default:
                record.name = f"{category_label} (Default)"
            else:
                mt_name = record.maintenance_type_id.name if record.maintenance_type_id else "N/A"
                record.name = f"{category_label} - {mt_name}"

    @api.constrains("is_default", "category", "active")
    def _check_single_default_per_category(self):
        """Validation 6.1: Only one default active rule per category."""
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
                        f"There is already a default approval rule for the '{record.category}' category. "
                        "Only one active default rule is allowed per category."
                    )

    @api.constrains("is_default", "maintenance_type_id")
    def _check_maintenance_type_required_for_specific(self):
        """Non-default matrices must have a maintenance type."""
        for record in self:
            if not record.is_default and not record.maintenance_type_id:
                raise ValidationError(
                    "Maintenance Type is required for non-default approval matrices."
                )

    @api.constrains("approval_line_ids")
    def _check_has_approval_lines(self):
        """Validation 6.1: Must have at least one approval line."""
        for record in self:
            if not record.approval_line_ids:
                raise ValidationError(
                    "Approval matrix must have at least one approval line."
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
        help="Approval order — lower sequence is approved first."
    )
    starting_amount = fields.Monetary(
        string="Starting Amount",
        required=True,
        default=0,
        help=(
            "Threshold: this approver is required when SPK total amount >= this value. "
            "Example: 0=Supervisor, 5,000,000=Manager, 10,000,000=Director."
        )
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        ondelete="restrict",
        default=lambda self: self.env.ref("base.IDR"),
    )
    approver_id = fields.Many2one(
        "res.users",
        string="Approver",
        required=True,
        ondelete="restrict",
    )
    # Delegate is optional
    delegate_id = fields.Many2one(
        "res.users",
        string="Delegate",
        required=False,
        ondelete="restrict",
        help="User who can approve on behalf of the Approver during the delegation validity period."
    )
    # Delegation validity period — only the delegate has a time restriction
    delegate_valid_from = fields.Date(
        string="Delegate Valid From",
        help="Start of delegation period. Leave empty for no lower bound."
    )
    delegate_valid_to = fields.Date(
        string="Delegate Valid To",
        help="End of delegation period. Leave empty for no upper bound."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
    )

    @api.constrains("delegate_valid_from", "delegate_valid_to")
    def _check_delegate_date_validity(self):
        """Delegate Valid From must be before or equal to Delegate Valid To."""
        for record in self:
            if record.delegate_valid_from and record.delegate_valid_to:
                if record.delegate_valid_from > record.delegate_valid_to:
                    raise ValidationError(
                        "Delegate Valid From date must be earlier than or equal to Delegate Valid To date."
                    )

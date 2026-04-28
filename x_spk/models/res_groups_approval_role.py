from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ResGroupsApprovalRole(models.Model):
    _name = "res.groups.approval.role"
    _description = "Approval Role Master"
    _order = "sequence asc"

    name = fields.Char(
        string="Role Name",
        required=True,
        unique=True,
        help="Name of the approval role (e.g., Manager, Senior Manager, Director)"
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Role hierarchy level (lower number = lower level)"
    )
    description = fields.Text(
        string="Description",
        help="Description of this approval role and its responsibilities"
    )
    user_id = fields.Many2one(
        "res.users",
        string="Assigned User",
        help="The user assigned to this approval role (One-to-One mapping)"
    )
    active = fields.Boolean(
        string="Active",
        default=True,
    )

    _sql_constraints = [
        ("unique_name", "UNIQUE(name)", "Role name must be unique"),
    ]

    @api.constrains("user_id")
    def _check_unique_user_per_role(self):
        """Ensure each user is assigned to only one approval role (One-to-One)"""
        for record in self:
            if record.user_id:
                duplicate = self.search([
                    ("user_id", "=", record.user_id.id),
                    ("id", "!=", record.id),
                ])
                if duplicate:
                    raise ValidationError(
                        f"User '{record.user_id.display_name}' is already assigned to role "
                        f"'{duplicate[0].name}'. Each user can only be assigned to one approval role."
                    )

    @api.model
    def get_user_for_role(self, role_name):
        """Get the user assigned to a specific role by name
        Returns: res.users record or False
        """
        role = self.search([
            ("name", "=", role_name),
            ("active", "=", True),
        ], limit=1)
        return role.user_id if role else False

    @api.model
    def get_role_for_user(self, user_id):
        """Get the approval role assigned to a specific user
        Args: user_id (int or res.users record)
        Returns: res.groups.approval.role record or False
        """
        if isinstance(user_id, int):
            user = self.env["res.users"].browse(user_id)
        else:
            user = user_id
        
        role = self.search([
            ("user_id", "=", user.id),
            ("active", "=", True),
        ], limit=1)
        return role if role else False

    def name_get(self):
        """Display role name with sequence context"""
        result = []
        for record in self:
            display_name = f"[{record.sequence}] {record.name}"
            if record.user_id:
                display_name += f" ({record.user_id.display_name})"
            result.append((record.id, display_name))
        return result

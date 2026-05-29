from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Command, Domain


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    def _default_allowed_user_ids(self):
        admin = self.env.ref("base.user_admin", raise_if_not_found=False)
        return [Command.link(admin.id)] if admin else False

    @api.model
    def _set_default_allowed_admin(self):
        admin = self.env.ref("base.user_admin", raise_if_not_found=False)
        if not admin:
            return

        picking_types = self.sudo().search([("allowed_user_ids", "=", False)])
        picking_types.write({"allowed_user_ids": [Command.link(admin.id)]})

    allowed_user_ids = fields.Many2many(
        "res.users",
        "stock_picking_type_allowed_user_rel",
        "picking_type_id",
        "user_id",
        string="Allowed Users",
        default=_default_allowed_user_ids,
        domain=[("share", "=", False)],
        help="Only listed users can see and open this operation type in Inventory Overview "
             "and related transfer actions. New operation types default to Administrator only.",
    )

    def _is_allowed_for_current_user(self):
        self.ensure_one()
        return self.env.user in self.allowed_user_ids

    def _check_allowed_for_current_user(self):
        for picking_type in self:
            if not picking_type._is_allowed_for_current_user():
                raise AccessError(
                    "You are not allowed to access operation type: %s"
                    % picking_type.display_name
                )

    def _get_action(self, action_xmlid):
        self._check_allowed_for_current_user()
        action = super()._get_action(action_xmlid)
        allowed_domain = self.env["stock.picking"]._operation_type_allowed_domain()
        action["domain"] = Domain.AND([action.get("domain") or [], allowed_domain])
        return action

    def get_action_picking_type_moves_analysis(self):
        self._check_allowed_for_current_user()
        action = super().get_action_picking_type_moves_analysis()
        allowed_domain = self.env["stock.move"]._operation_type_allowed_domain()
        action["domain"] = Domain.AND([action.get("domain") or [], allowed_domain])
        return action


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _operation_type_allowed_domain(self):
        return [("picking_type_id.allowed_user_ids", "in", [self.env.uid])]


class StockMove(models.Model):
    _inherit = "stock.move"

    def _operation_type_allowed_domain(self):
        return [("picking_type_id.allowed_user_ids", "in", [self.env.uid])]


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _operation_type_allowed_domain(self):
        return [("picking_type_id.allowed_user_ids", "in", [self.env.uid])]

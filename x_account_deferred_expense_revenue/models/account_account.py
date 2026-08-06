from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountAccount(models.Model):
    _inherit = "account.account"

    deferred_automation = fields.Selection(
        [
            ("no", "No"),
            ("draft", "Create in draft"),
            ("validate", "Create and validate"),
        ],
        string="Automate Deferred",
        default="no",
        required=True,
    )
    deferred_model_id = fields.Many2one(
        "account.deferred.model",
        string="Deferred Model",
        check_company=True,
        domain="[('company_id', 'in', company_ids)]",
    )
    deferred_manage_items = fields.Boolean(string="Manage Items", default=True)

    @api.onchange("account_type")
    def _onchange_deferred_account_type(self):
        for account in self:
            if account.account_type not in ("asset_current", "liability_current"):
                account.deferred_automation = "no"
                account.deferred_model_id = False

    @api.constrains("account_type", "deferred_automation", "deferred_model_id")
    def _check_deferred_automation(self):
        for account in self:
            if account.deferred_automation == "no":
                continue
            if account.account_type not in ("asset_current", "liability_current"):
                raise ValidationError(_("Deferred automation is only available for Current Assets and Current Liabilities accounts."))
            if not account.deferred_model_id:
                raise ValidationError(_("Please set a Deferred Model."))
            if account.account_type == "asset_current" and account.deferred_model_id.deferred_type != "expense":
                raise ValidationError(_("Current Assets accounts can only use Deferred Expense models."))
            if account.account_type == "liability_current" and account.deferred_model_id.deferred_type != "revenue":
                raise ValidationError(_("Current Liabilities accounts can only use Deferred Revenue models."))

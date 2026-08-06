from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountDeferredModel(models.Model):
    _name = "account.deferred.model"
    _description = "Deferred Expense / Revenue Model"
    _check_company_auto = True

    name = fields.Char(required=True)
    deferred_type = fields.Selection(
        [
            ("expense", "Deferred Expense"),
            ("revenue", "Deferred Revenue"),
        ],
        required=True,
        default="expense",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    method = fields.Selection(
        [("linear", "Straight Line")],
        required=True,
        default="linear",
    )
    method_number = fields.Integer(string="Duration", required=True, default=12)
    method_period = fields.Integer(string="Period Length", required=True, default=1)
    period_unit = fields.Selection([("month", "Months")], default="month", required=True)
    computation = fields.Selection(
        [("constant", "Constant Periods")],
        default="constant",
        required=True,
    )
    deferred_account_id = fields.Many2one(
        "account.account",
        string="Deferred Account",
        required=True,
        check_company=True,
        domain="[('company_ids', 'in', [company_id])]",
    )
    recognition_account_id = fields.Many2one(
        "account.account",
        string="Recognition Account",
        required=True,
        check_company=True,
        domain="[('company_ids', 'in', [company_id])]",
    )
    journal_id = fields.Many2one(
        "account.journal",
        required=True,
        check_company=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )
    prorata = fields.Boolean(string="Prorata Date")
    first_recognition = fields.Selection(
        [
            ("invoice_date", "Invoice/Bill Date"),
            ("next_month", "First Day of Next Month"),
        ],
        default="next_month",
        required=True,
    )
    active = fields.Boolean(default=True)

    @api.constrains("method_number", "method_period")
    def _check_duration(self):
        for model in self:
            if model.method_number <= 0:
                raise ValidationError(_("Duration must be greater than zero."))
            if model.method_period <= 0:
                raise ValidationError(_("Period length must be greater than zero."))

    @api.constrains("deferred_type", "deferred_account_id", "recognition_account_id")
    def _check_accounts(self):
        for model in self:
            if model.deferred_account_id == model.recognition_account_id:
                raise ValidationError(_("Deferred account and recognition account must be different."))
            deferred_type = model.deferred_account_id.account_type
            if model.deferred_type == "expense" and deferred_type != "asset_current":
                raise ValidationError(_("Deferred Expense models must use a Current Assets deferred account."))
            if model.deferred_type == "revenue" and deferred_type != "liability_current":
                raise ValidationError(_("Deferred Revenue models must use a Current Liabilities deferred account."))

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import format_date


class AssetModify(models.TransientModel):
    _inherit = "asset.modify"

    ar_account_id = fields.Many2one(
        "account.account",
        check_company=True,
        domain="[('is_ar_account', '=', True)]",
        string="A/R Account",
        help="Receivable account debited with the leaseback A/R Amount.",
    )
    ar_amount = fields.Monetary(
        string="A/R Amount",
        help="Proceeds of the leaseback. Compared to the asset book value to "
        "determine the deferred gain/loss.",
    )
    deferred_pl_account_id = fields.Many2one(
        "account.account",
        check_company=True,
        domain="[('is_deferred_pl_account', '=', True)]",
        string="Deferred Profit/Loss Account",
        compute="_compute_deferred_pl_account",
        store=True,
        readonly=False,
        compute_sudo=True,
        help="Account receiving the gain/loss of the leaseback versus the asset "
        "book value (e.g. 501409 Laba Rugi Ditangguhkan).",
    )

    @api.depends("asset_id")
    def _get_selection_modify_options(self):
        options = super()._get_selection_modify_options()
        if self.env.context.get("resume_after_pause"):
            return options
        result = []
        for option in options:
            result.append(option)
            if option[0] == "sell":
                result.append(("leaseback", _("Leaseback")))
        return result

    @api.depends("company_id")
    def _compute_deferred_pl_account(self):
        for record in self:
            record.deferred_pl_account_id = record.company_id._get_leaseback_deferred_account()

    @api.depends("asset_id", "invoice_ids", "invoice_line_ids", "modify_action", "date", "ar_amount")
    def _compute_gain_or_loss(self):
        super()._compute_gain_or_loss()
        for record in self.filtered(lambda r: r.modify_action == "leaseback"):
            comparison = record.company_id.currency_id.compare_amounts(
                record.asset_id._get_own_book_value(record.date), record.ar_amount
            )
            if comparison < 0:
                record.gain_or_loss = "gain"
            elif comparison > 0:
                record.gain_or_loss = "loss"
            else:
                record.gain_or_loss = "no"

    def _compute_informational_text(self):
        super()._compute_informational_text()
        for wizard in self.filtered(lambda r: r.modify_action == "leaseback"):
            account = wizard.deferred_pl_account_id.display_name or ""
            if wizard.gain_or_loss == "gain":
                result = _("a gain")
            elif wizard.gain_or_loss == "loss":
                result = _("a loss")
            else:
                result = _("no gain/loss")
            wizard.informational_text = _(
                "A depreciation entry will be posted on and including the date %(date)s."
                "<br/> A leaseback entry (no invoice) will book the A/R amount and "
                "%(result)s versus the book value on the deferred account "
                "<b>%(account)s</b>.",
                date=format_date(self.env, wizard.date),
                result=result,
                account=account,
            )

    def action_leaseback(self):
        self.ensure_one()
        if not self.ar_account_id:
            raise UserError(_("Please set the A/R Account for the leaseback."))
        if self.company_id.currency_id.compare_amounts(self.ar_amount, 0) <= 0:
            raise UserError(_("Please set a positive A/R Amount for the leaseback."))
        if not self.deferred_pl_account_id:
            raise UserError(_(
                "Please set the Leaseback Deferred Profit/Loss account "
                "(e.g. 501409) in Accounting Settings or on this wizard."
            ))
        return self.asset_id.set_to_close_leaseback(
            ar_account=self.ar_account_id,
            ar_amount=self.ar_amount,
            deferred_account=self.deferred_pl_account_id,
            date=self.date,
            message=self.name,
        )

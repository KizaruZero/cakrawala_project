from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    x_writeoff_line_ids = fields.One2many(
        comodel_name='x.payment.register.writeoff.line',
        inverse_name='wizard_id',
        string="Write-Off Lines",
        help="Split the payment difference over several accounts when the invoice/bill is marked as fully paid.",
    )
    x_writeoff_remaining = fields.Monetary(
        string="Remaining Difference",
        currency_field='currency_id',
        compute='_compute_x_writeoff_remaining',
        help="Payment difference not yet allocated to a write-off line.",
    )

    @api.depends('payment_difference', 'x_writeoff_line_ids.amount')
    def _compute_x_writeoff_remaining(self):
        for wizard in self:
            wizard.x_writeoff_remaining = wizard.payment_difference - sum(wizard.x_writeoff_line_ids.mapped('amount'))

    def _x_use_writeoff_lines(self):
        """ The multi-account table replaces the standard single write-off account. """
        self.ensure_one()
        return (
            self.payment_difference_handling == 'reconcile'
            and not self.early_payment_discount_mode
            and not self.currency_id.is_zero(self.payment_difference)
        )

    def _x_check_writeoff_lines(self):
        self.ensure_one()
        lines = self.x_writeoff_line_ids
        if not lines:
            raise UserError(_("Please add at least one line to post the payment difference (Mark as fully paid)."))
        if lines.filtered(lambda line: not line.account_id):
            raise UserError(_("Please set an account on every payment difference line."))
        if not self.currency_id.is_zero(self.x_writeoff_remaining):
            raise UserError(_(
                "The total of the payment difference lines (%(total)s) must be equal to the payment difference (%(difference)s).",
                total=self.currency_id.format(sum(lines.mapped('amount'))),
                difference=self.currency_id.format(self.payment_difference),
            ))

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        if not self._x_use_writeoff_lines():
            return payment_vals

        self._x_check_writeoff_lines()
        # Same sign convention as the standard write-off: receiving money credits
        # the write-off account, sending money debits it.
        sign = 1 if self.payment_type == 'inbound' else -1
        write_off_line_vals = []
        for line in self.x_writeoff_line_ids:
            if self.currency_id.is_zero(line.amount):
                continue
            amount_currency = sign * line.amount
            vals = {
                'name': line.name or self.writeoff_label,
                'account_id': line.account_id.id,
                'partner_id': self.partner_id.id,
                'currency_id': self.currency_id.id,
                'amount_currency': amount_currency,
                'balance': self.currency_id._convert(amount_currency, self.company_id.currency_id, self.company_id, self.payment_date),
            }
            if line.analytic_distribution:
                vals['analytic_distribution'] = line.analytic_distribution
            write_off_line_vals.append(vals)

        payment_vals['write_off_line_vals'] = write_off_line_vals
        payment_vals.pop('force_balance', None)
        return payment_vals


class XPaymentRegisterWriteoffLine(models.TransientModel):
    _name = 'x.payment.register.writeoff.line'
    _inherit = ['analytic.mixin']
    _description = "Payment Register Write-Off Line"
    _check_company_auto = True

    wizard_id = fields.Many2one(
        comodel_name='account.payment.register',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(related='wizard_id.company_id')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    account_id = fields.Many2one(
        comodel_name='account.account',
        string="Account",
        required=True,
        check_company=True,
    )
    name = fields.Char(string="Label")
    amount = fields.Monetary(
        string="Amount",
        currency_field='currency_id',
        help="Part of the payment difference posted to this account (same sign as the payment difference).",
    )

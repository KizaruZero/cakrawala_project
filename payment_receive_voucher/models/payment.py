from odoo import api, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        active_model = self.env.context.get('active_model')
        active_ids = self.env.context.get('active_ids', [])
        if active_model == 'account.move':
            self.env['account.move'].browse(active_ids)._prv_check_payment()
        elif active_model == 'account.move.line':
            self.env['account.move.line'].browse(active_ids).move_id._prv_check_payment()
        return values

    def _create_payments(self):
        self.line_ids.move_id._prv_check_payment()
        return super()._create_payments()


class AccountPartialReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    @api.model_create_multi
    def create(self, vals_list):
        # Also protects matching standalone payments, bank lines and credit notes.
        ids = {v[k] for v in vals_list for k in ('debit_move_id', 'credit_move_id') if v.get(k)}
        lines = self.env['account.move.line'].browse(list(ids))
        lines.filtered(lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')).move_id._prv_check_payment()
        return super().create(vals_list)

    def write(self, vals):
        if {'debit_move_id', 'credit_move_id', 'amount', 'debit_amount_currency', 'credit_amount_currency'}.intersection(vals):
            ids = [vals[k] for k in ('debit_move_id', 'credit_move_id') if vals.get(k)]
            lines = self.debit_move_id | self.credit_move_id | self.env['account.move.line'].browse(ids)
            lines.filtered(lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')).move_id._prv_check_payment()
        return super().write(vals)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    @api.model_create_multi
    def create(self, vals_list):
        payments = super().create(vals_list)
        payments.invoice_ids._prv_check_payment()
        return payments

    def write(self, vals):
        if 'invoice_ids' in vals or 'state' in vals:
            self.invoice_ids._prv_check_payment()
        result = super().write(vals)
        if 'invoice_ids' in vals:
            self.invoice_ids._prv_check_payment()
        return result

    def action_post(self):
        self.invoice_ids._prv_check_payment()
        return super().action_post()

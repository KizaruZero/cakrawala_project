from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    prv_allow_partial_payment = fields.Boolean(compute='_compute_prv_allow_partial_payment')
    prv_has_configured_voucher = fields.Boolean(compute='_compute_prv_allow_partial_payment')
    prv_force_group_payment = fields.Boolean(compute='_compute_prv_force_group_payment')

    @api.depends('line_ids', 'line_ids.move_id.prv_voucher_id',
                 'line_ids.move_id.prv_voucher_id.state',
                 'line_ids.move_id.prv_voucher_id.config_id.allow_edit_amount_for_partial_payment')
    def _compute_prv_allow_partial_payment(self):
        for wizard in self:
            # Preserve Odoo behavior without an active voucher config. With a
            # config, use the configuration attached to each approved voucher.
            vouchers = wizard.line_ids.move_id.sudo().mapped('prv_voucher_id')
            configured = vouchers.filtered(
                lambda voucher: voucher.state == 'approved'
                and voucher.config_id and voucher.config_id.active
            )
            wizard.prv_has_configured_voucher = bool(configured)
            wizard.prv_allow_partial_payment = (
                all(voucher.config_id.allow_edit_amount_for_partial_payment for voucher in configured)
                if configured else True
            )

    @api.depends('can_edit_wizard', 'can_group_payments', 'prv_has_configured_voucher',
                 'prv_allow_partial_payment', 'batches')
    def _compute_prv_force_group_payment(self):
        for wizard in self:
            wizard.prv_force_group_payment = bool(
                wizard.prv_has_configured_voucher
                and wizard.prv_allow_partial_payment
                and wizard.can_edit_wizard
                and wizard.can_group_payments
                and len(wizard.batches) == 1
            )

    @api.depends('can_edit_wizard', 'can_group_payments', 'prv_force_group_payment')
    def _compute_group_payment(self):
        super()._compute_group_payment()
        for wizard in self:
            if wizard.prv_force_group_payment:
                # Odoo only applies an edited aggregate amount when payments
                # are grouped. Force grouping for the opted-in voucher case.
                wizard.group_payment = True

    def _prv_check_partial_payment_amount(self):
        for wizard in self:
            wizard._compute_prv_allow_partial_payment()
            if not wizard.prv_has_configured_voucher or not wizard.batches:
                continue
            amount_by_default = wizard._get_total_amounts_to_pay(wizard.batches)['amount_by_default']
            if not wizard.currency_id.compare_amounts(wizard.amount, amount_by_default):
                continue
            if not wizard.prv_allow_partial_payment:
                raise UserError(_('The voucher configuration does not allow editing the payment amount for a partial payment.'))
            edit_mode = wizard.can_edit_wizard and (
                len(wizard.batches[0]['lines']) == 1 or wizard.group_payment
            )
            if not edit_mode:
                raise UserError(_('Enable Group Payments to edit a partial amount across multiple bills/invoices.'))

    @api.model_create_multi
    def create(self, vals_list):
        wizards = super().create(vals_list)
        # The standard amount is computed from the selected payment lines; reject
        # forged custom amounts at wizard creation when partial payment is disabled.
        wizards._prv_check_partial_payment_amount()
        return wizards

    def write(self, vals):
        result = super().write(vals)
        if 'amount' in vals or 'payment_date' in vals or 'installments_mode' in vals:
            self._prv_check_partial_payment_amount()
        return result

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
        self._prv_check_partial_payment_amount()
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

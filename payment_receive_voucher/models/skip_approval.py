from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    skip_approval = fields.Boolean(
        string='Skip Approval', default=False, copy=False, tracking=True,
        help='Allow direct Pay without Payment/Receive Voucher approval for this invoice/bill only. '
             'Existing voucher history and approval state are not changed.',
    )

    def _prv_lock(self):
        result = super()._prv_lock()
        # Re-read under the same row lock as payment/voucher operations. Do not
        # trust a stale flag in an already-open payment wizard.
        if self:
            self.flush_recordset(['skip_approval'])
            self.invalidate_recordset(['skip_approval'])
        return result

    @api.constrains('skip_approval', 'move_type', 'state')
    def _check_skip_approval_document(self):
        for move in self.filtered('skip_approval'):
            if move.move_type not in ('in_invoice', 'out_invoice'):
                raise ValidationError(_('Skip Approval is only available on Customer Invoices and Vendor Bills.'))

    @api.model_create_multi
    def create(self, values_list):
        if any(values.get('skip_approval', self.env.context.get('default_skip_approval'))
               for values in values_list) and not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(_('Accounting access is required to set Skip Approval.'))
        return super().create(values_list)

    def write(self, values):
        if 'skip_approval' in values:
            self.check_access('write')
            self._prv_lock()
            changed = self.filtered(lambda move: move.skip_approval != bool(values['skip_approval']))
            if changed and not self.env.user.has_group('account.group_account_invoice'):
                raise AccessError(_('Accounting access is required to change Skip Approval.'))
            if changed.filtered(lambda move: move.state not in ('draft', 'posted')):
                raise UserError(_('Skip Approval can only be changed on Draft or Posted invoices/bills.'))
        return super().write(values)

    def _prv_check_payment(self, require_voucher_route=False):
        self._prv_lock()
        required = self.filtered(lambda move: not (
            move.skip_approval and move.move_type in ('in_invoice', 'out_invoice')))
        # Only the approval/route guard is skipped. Odoo's payment, reconciliation,
        # access, company, residual and posting validations still run normally.
        return super(AccountMove, required)._prv_check_payment(require_voucher_route=require_voucher_route)

    def _prv_check_new_voucher_skip_approval(self):
        self.check_access('read')
        self._prv_lock()
        if self.filtered('skip_approval'):
            raise UserError(_(
                'Cannot create a new voucher for documents with Skip Approval enabled. '
                'Use Pay directly, or clear Skip Approval before creating a voucher.'))

    def _prv_create_voucher(self, kind):
        self._prv_check_new_voucher_skip_approval()
        return super()._prv_create_voucher(kind)

    def _prv_validate_selection(self, voucher_type, current=None, payment_voucher_type=None,
                                defer_partner=False):
        if not current:
            # Covers list actions, the create wizard and direct voucher creation.
            self._prv_check_new_voucher_skip_approval()
        return super()._prv_validate_selection(
            voucher_type, current=current, payment_voucher_type=payment_voucher_type,
            defer_partner=defer_partner)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.depends('line_ids', 'line_ids.move_id.skip_approval', 'line_ids.move_id.prv_voucher_id',
                 'line_ids.move_id.prv_voucher_id.state',
                 'line_ids.move_id.prv_voucher_id.config_id.active',
                 'line_ids.move_id.prv_voucher_id.config_id.allow_edit_amount_for_partial_payment')
    def _compute_prv_allow_partial_payment(self):
        for wizard in self:
            required = wizard.line_ids.move_id.filtered(lambda move: not move.skip_approval)
            vouchers = required.sudo().mapped('prv_voucher_id')
            configured = vouchers.filtered(lambda voucher: voucher.state == 'approved'
                                          and voucher.config_id and voucher.config_id.active)
            wizard.prv_has_configured_voucher = bool(configured)
            wizard.prv_allow_partial_payment = (
                all(voucher.config_id.allow_edit_amount_for_partial_payment for voucher in configured)
                if configured else True)

    def _prv_check_partial_payment_amount(self):
        result = super()._prv_check_partial_payment_amount()
        for wizard in self:
            sources = wizard.line_ids.move_id
            sources._prv_lock()
            if not sources.filtered('skip_approval'):
                continue
            # An old voucher or a second open wizard must not pay an obsolete
            # original amount after direct Pay has reduced the residual.
            wizard.line_ids.invalidate_recordset(['amount_residual', 'amount_residual_currency'])
            wizard.invalidate_recordset(['batches'])
            if wizard.batches:
                amounts = wizard._get_total_amounts_to_pay(wizard.batches)
                maximum = max(amounts['full_amount'], amounts['full_amount_for_difference'])
                if wizard.currency_id.compare_amounts(wizard.amount, maximum) > 0:
                    raise UserError(_('Payment amount cannot exceed the current outstanding balance. Reopen Pay to refresh the amount.'))
        return result

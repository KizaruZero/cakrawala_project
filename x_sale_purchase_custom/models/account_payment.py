# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    is_internal_transfer_custom = fields.Boolean(
        string='Is Internal Transfer',
        default=False,
        tracking=True,
        copy=False,
    )
    payment_type_ui = fields.Selection(
        selection=[
            ('outbound', 'Send'),
            ('inbound', 'Receive'),
            ('internal_transfer', 'Internal Transfer'),
        ],
        string='Payment Type',
        default='inbound',
        required=True,
        tracking=True,
        copy=False,
    )
    internal_transfer_direction = fields.Selection(
        selection=[
            ('inbound', 'Receive (Uang Masuk)'),
            ('outbound', 'Send (Uang Keluar)'),
        ],
        string='Transfer Direction',
        default='inbound',
        tracking=True,
        copy=False,
    )
    custom_destination_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Destination Account',
        check_company=True,
        copy=False,
        tracking=True,
        domain="[('account_type', '!=', 'off_balance')]",
        help='Akun COA lawan dari akun Bank saat Journal Entry Internal Transfer terbentuk.',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        pay_type = res.get('payment_type') or self.env.context.get('default_payment_type') or 'inbound'
        if pay_type not in ('inbound', 'outbound'):
            pay_type = 'inbound'
        is_internal = bool(
            res.get('is_internal_transfer_custom')
            or self.env.context.get('default_is_internal_transfer_custom')
            or self.env.context.get('default_payment_type_ui') == 'internal_transfer'
        )
        if 'internal_transfer_direction' in fields_list and 'default_internal_transfer_direction' not in self.env.context:
            res['internal_transfer_direction'] = pay_type
        if 'payment_type_ui' in fields_list and 'default_payment_type_ui' not in self.env.context:
            res['payment_type_ui'] = 'internal_transfer' if is_internal else pay_type
        if is_internal and 'is_internal_transfer_custom' in fields_list:
            res['is_internal_transfer_custom'] = True
        return res

    @api.onchange('payment_type_ui')
    def _onchange_payment_type_ui(self):
        for pay in self:
            if pay.payment_type_ui == 'internal_transfer':
                direction = pay.internal_transfer_direction or pay.payment_type or 'inbound'
                if direction not in ('inbound', 'outbound'):
                    direction = 'inbound'
                pay.is_internal_transfer_custom = True
                pay.internal_transfer_direction = direction
                pay.payment_type = direction
            elif pay.payment_type_ui in ('inbound', 'outbound'):
                pay.is_internal_transfer_custom = False
                pay.payment_type = pay.payment_type_ui
                pay.internal_transfer_direction = pay.payment_type_ui
                pay.custom_destination_account_id = False

    @api.onchange('internal_transfer_direction')
    def _onchange_internal_transfer_direction(self):
        for pay in self:
            if pay.is_internal_transfer_custom and pay.internal_transfer_direction in ('inbound', 'outbound'):
                pay.payment_type = pay.internal_transfer_direction

    def _normalize_internal_transfer_vals(self, vals, existing_record=None):
        """Keep payment_type_ui, is_internal_transfer_custom, direction, and payment_type synchronized."""
        vals = dict(vals)
        if 'payment_type_ui' in vals:
            ui_type = vals['payment_type_ui']
            if ui_type == 'internal_transfer':
                vals['is_internal_transfer_custom'] = True
                direction = (
                    vals.get('internal_transfer_direction')
                    or (existing_record.internal_transfer_direction if existing_record else False)
                    or vals.get('payment_type')
                    or (existing_record.payment_type if existing_record else False)
                    or self.env.context.get('default_payment_type')
                    or 'inbound'
                )
                if direction not in ('inbound', 'outbound'):
                    direction = 'inbound'
                vals['internal_transfer_direction'] = direction
                vals['payment_type'] = direction
            elif ui_type in ('inbound', 'outbound'):
                vals['is_internal_transfer_custom'] = False
                vals['payment_type'] = ui_type
                vals['internal_transfer_direction'] = ui_type
                vals.setdefault('custom_destination_account_id', False)
        elif 'is_internal_transfer_custom' in vals:
            if vals['is_internal_transfer_custom']:
                direction = (
                    vals.get('internal_transfer_direction')
                    or vals.get('payment_type')
                    or (existing_record.internal_transfer_direction if existing_record else False)
                    or (existing_record.payment_type if existing_record else False)
                    or self.env.context.get('default_payment_type')
                    or 'inbound'
                )
                if direction not in ('inbound', 'outbound'):
                    direction = 'inbound'
                vals['payment_type_ui'] = 'internal_transfer'
                vals['internal_transfer_direction'] = direction
                vals['payment_type'] = direction
            else:
                pay_type = (
                    vals.get('payment_type')
                    or (existing_record.payment_type if existing_record else False)
                    or self.env.context.get('default_payment_type')
                    or 'inbound'
                )
                if pay_type not in ('inbound', 'outbound'):
                    pay_type = 'inbound'
                vals['payment_type_ui'] = pay_type
                vals['payment_type'] = pay_type
                vals['internal_transfer_direction'] = pay_type
        elif existing_record is None:
            # Programmatic create() without payment_type_ui (e.g., Register Payment wizard)
            pay_type = vals.get('payment_type') or self.env.context.get('default_payment_type') or 'inbound'
            if pay_type not in ('inbound', 'outbound'):
                pay_type = 'inbound'
            vals['payment_type_ui'] = pay_type
            vals.setdefault('internal_transfer_direction', pay_type)
        elif (
            'internal_transfer_direction' in vals
            and vals['internal_transfer_direction'] in ('inbound', 'outbound')
            and existing_record.is_internal_transfer_custom
        ):
            vals['payment_type'] = vals['internal_transfer_direction']
        elif (
            'payment_type' in vals
            and vals['payment_type'] in ('inbound', 'outbound')
            and not existing_record.is_internal_transfer_custom
        ):
            vals['payment_type_ui'] = vals['payment_type']
            vals.setdefault('internal_transfer_direction', vals['payment_type'])
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        normalized_list = [self._normalize_internal_transfer_vals(vals, existing_record=None) for vals in vals_list]
        return super().create(normalized_list)

    def write(self, vals):
        trigger_keys = {
            'payment_type_ui',
            'is_internal_transfer_custom',
            'internal_transfer_direction',
            'payment_type',
        }
        if trigger_keys.intersection(vals):
            if len(self) == 1:
                vals = self._normalize_internal_transfer_vals(vals, existing_record=self)
                return super().write(vals)
            res = True
            for rec in self:
                rec_vals = rec._normalize_internal_transfer_vals(vals, existing_record=rec)
                res = super(AccountPayment, rec).write(rec_vals) and res
            return res
        return super().write(vals)

    @api.depends('journal_id', 'partner_id', 'partner_type', 'is_internal_transfer_custom', 'custom_destination_account_id')
    def _compute_destination_account_id(self):
        internal_payments = self.filtered('is_internal_transfer_custom')
        for pay in internal_payments:
            pay.destination_account_id = pay.custom_destination_account_id
        super(AccountPayment, self - internal_payments)._compute_destination_account_id()

    @api.depends('payment_method_line_id', 'journal_id', 'is_internal_transfer_custom', 'payment_type')
    def _compute_outstanding_account_id(self):
        super()._compute_outstanding_account_id()
        for pay in self.filtered('is_internal_transfer_custom'):
            if not pay.outstanding_account_id:
                pay.outstanding_account_id = (
                    pay.journal_id.default_account_id
                    or pay._get_outstanding_account(pay.payment_type)
                )

    def _seek_for_lines(self):
        self.ensure_one()
        if not self.is_internal_transfer_custom or not self.move_id:
            return super()._seek_for_lines()

        liquidity_lines = self.env['account.move.line']
        counterpart_lines = self.env['account.move.line']
        writeoff_lines = self.env['account.move.line']
        dest_account = self.custom_destination_account_id or self.destination_account_id
        valid_liquidity = self._get_valid_liquidity_accounts()

        for line in self.move_id.line_ids:
            if not liquidity_lines and line.account_id in valid_liquidity and line.account_id != dest_account:
                liquidity_lines += line
            elif dest_account and line.account_id == dest_account and not counterpart_lines:
                counterpart_lines += line
            elif line.account_id in valid_liquidity and not liquidity_lines:
                liquidity_lines += line
            else:
                writeoff_lines += line

        if len(writeoff_lines) == 1:
            if not liquidity_lines:
                liquidity_lines = writeoff_lines
                writeoff_lines = self.env['account.move.line']
            elif not counterpart_lines:
                counterpart_lines = writeoff_lines
                writeoff_lines = self.env['account.move.line']

        return [liquidity_lines, counterpart_lines, writeoff_lines]

    @api.model
    def _get_trigger_fields_to_synchronize(self):
        return super()._get_trigger_fields_to_synchronize() + (
            'is_internal_transfer_custom',
            'internal_transfer_direction',
            'custom_destination_account_id',
        )

    @api.constrains('is_internal_transfer_custom', 'custom_destination_account_id', 'journal_id', 'payment_method_line_id')
    def _check_internal_transfer_destination_account(self):
        for pay in self:
            if not pay.is_internal_transfer_custom:
                continue
            if not pay.custom_destination_account_id:
                raise ValidationError(_(
                    'Destination Account wajib dipilih ketika Payment Type adalah Internal Transfer.'
                ))
            bank_account = pay.outstanding_account_id or pay.journal_id.default_account_id
            if bank_account and pay.custom_destination_account_id == bank_account:
                raise ValidationError(_(
                    'Destination Account (%s) tidak boleh sama dengan akun Bank pada jurnal pembayaran (%s).',
                    pay.custom_destination_account_id.display_name,
                    bank_account.display_name,
                ))

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

ACTIVE = ('draft', 'waiting', 'approved')
MOVE_LOCK_FIELDS = {'state', 'partner_id', 'company_id', 'currency_id', 'move_type',
    'invoice_line_ids', 'line_ids', 'invoice_date', 'invoice_date_due', 'date',
    'invoice_payment_term_id', 'fiscal_position_id', 'invoice_cash_rounding_id',
    'invoice_currency_rate', 'journal_id', 'partner_bank_id', 'payment_reference', 'ref',
    'name', 'amount_total', 'amount_tax', 'amount_untaxed', 'amount_residual',
    'amount_total_signed', 'amount_tax_signed', 'amount_untaxed_signed', 'amount_residual_signed'}
LINE_LOCK_FIELDS = {'move_id', 'account_id', 'partner_id', 'company_id', 'currency_id',
    'product_id', 'name', 'quantity', 'price_unit', 'discount', 'tax_ids',
    'analytic_distribution', 'debit', 'credit', 'balance', 'amount_currency',
    'date_maturity', 'display_type', 'tax_line_id', 'tax_repartition_line_id',
    'product_uom_id', 'price_subtotal', 'price_total'}


class AccountMove(models.Model):
    _inherit = 'account.move'

    prv_voucher_id = fields.Many2one('prv.voucher', string='Voucher', readonly=True,
                                       copy=False, ondelete='restrict', index=True)
    # Reverse side of prv.voucher.move_ids. This relation is the durable history;
    # prv_voucher_id remains the latest voucher pointer for existing integrations.
    prv_voucher_ids = fields.Many2many(
        'prv.voucher', 'prv_voucher_move_rel', 'move_id', 'voucher_id',
        string='Vouchers', readonly=True, copy=False,
    )
    prv_voucher_state = fields.Selection(related='prv_voucher_id.state', string='Voucher Status')
    prv_voucher_approved = fields.Boolean(compute='_compute_prv_info', string='Voucher Approved')
    prv_voucher_info = fields.Char(compute='_compute_prv_info', string='Approval Info')
    prv_approved_remarks = fields.Text(related='prv_voucher_id.approved_remarks', string='Approved Remarks')
    prv_receive_voucher_configured = fields.Boolean(compute='_compute_prv_receive_voucher_configured')

    @api.depends('company_id')
    def _compute_prv_receive_voucher_configured(self):
        companies = self.mapped('company_id')
        configs = self.env['prv.voucher.config'].sudo().search([
            ('company_id', 'in', companies.ids),
            ('voucher_type', '=', 'receive'),
            ('active', '=', True),
        ])
        configured_company_ids = set(configs.company_id.ids)
        for move in self:
            move.prv_receive_voucher_configured = move.company_id.id in configured_company_ids

    @api.depends('prv_voucher_id.state', 'prv_voucher_id.approved_at', 'prv_voucher_id.approved_by_id')
    def _compute_prv_info(self):
        for move in self:
            voucher = move.sudo().prv_voucher_id
            move.prv_voucher_approved = voucher.state == 'approved'
            move.prv_voucher_info = (_('Approved by %(user)s at %(date)s',
                user=voucher.approved_by_id.display_name, date=voucher.approved_at)
                if voucher.state == 'approved' else _('Not approved') if voucher else _('No voucher linked'))

    def _prv_lock(self):
        if self:
            self.check_access('read')
            self.flush_recordset(['prv_voucher_id', 'prv_voucher_ids'])
            self.env.cr.execute('SELECT id FROM account_move WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(self.ids)])
            self.invalidate_recordset(['prv_voucher_id', 'prv_voucher_ids', 'state', 'amount_residual', 'payment_state'])

    def _prv_set_voucher(self, voucher):
        result = super(AccountMove, self.sudo()).write({'prv_voucher_id': voucher.id})
        self.invalidate_recordset(['prv_voucher_ids'])
        return result

    def _prv_clear_voucher(self, voucher):
        """Restore the latest remaining reference without deleting voucher history."""
        linked = self.sudo().filtered(lambda move: move.prv_voucher_id == voucher)
        for move in linked:
            remaining = move.prv_voucher_ids - voucher
            remaining.invalidate_recordset(['state'])
            active = remaining.filtered(lambda candidate: candidate.state in ACTIVE)
            previous = (active or remaining).sorted('id')[-1:]
            super(AccountMove, move).write({'prv_voucher_id': previous.id or False})
        return True

    def _prv_validate_selection(self, voucher_type, current=None, payment_voucher_type=None,
                                defer_partner=False):
        expected = {'payment': 'in_invoice', 'receive': 'out_invoice'}.get(voucher_type)
        if not self or not expected or any(m.move_type != expected or m.state != 'posted' for m in self):
            raise UserError(_('Select posted vendor bills for Payment Voucher or posted customer invoices for Receive Voucher.'))
        if len(self.company_id) != 1 or len(self.currency_id) != 1:
            raise UserError(_('All selected documents must have the same company and currency.'))
        if self.company_id not in self.env.companies:
            raise AccessError(_('Select a company you are allowed to access.'))
        config = self.env['prv.voucher.config'].get_for_voucher(
            self.company_id, voucher_type, payment_voucher_type)
        if not defer_partner and (not config or config.require_same_partner) and len(self.partner_id) != 1:
            raise UserError(_('This voucher configuration requires all selected documents to have the same vendor or customer.'))
        if any(m.amount_residual <= 0 or m.payment_state in ('paid', 'in_payment', 'reversed', 'blocked') for m in self):
            raise UserError(_('Select unpaid or partially paid documents with a positive outstanding balance, not blocked or already in payment.'))
        for move in self:
            linked = move.sudo().prv_voucher_ids
            linked.invalidate_recordset(['state'])
            active = linked.filtered(lambda voucher: voucher.state in ACTIVE and voucher != current)
            if active:
                details = ', '.join('%s (%s)' % (voucher.name, voucher.state) for voucher in active)
                raise UserError(_('%(bill)s is already linked to active voucher(s): %(vouchers)s.',
                                  bill=move.display_name, vouchers=details))

    def _prv_check_payment(self, require_voucher_route=False):
        moves = self.filtered(lambda m: m.move_type in ('in_invoice', 'out_invoice'))
        moves._prv_lock()
        configs = self.env['prv.voucher.config'].sudo().search([
            ('company_id', 'in', moves.company_id.ids), ('active', '=', True),
        ])
        enabled = {(c.company_id.id, c.voucher_type) for c in configs}
        for move in moves:
            kind = 'payment' if move.move_type == 'in_invoice' else 'receive'
            if (move.company_id.id, kind) not in enabled:
                continue
            voucher = move.sudo().prv_voucher_id
            voucher.invalidate_recordset(['state'])
            if (move.state != 'posted' or not voucher or voucher.state != 'approved'
                    or voucher.voucher_type != kind or move not in voucher.move_ids):
                raise UserError(_('Payment is blocked: %(bill)s requires an approved %(kind)s voucher.',
                                  bill=move.display_name, kind=kind))
            snapshot = voucher.bill_ids.filtered(lambda b: b.move_id == move)
            if (len(snapshot) != 1
                    or (voucher.same_partner_required and voucher.partner_id != move.partner_id)
                    or voucher.company_id != move.company_id or voucher.currency_id != move.currency_id
                    or move.currency_id.compare_amounts(move.amount_total, snapshot.original_total)
                    or move.currency_id.compare_amounts(move.amount_residual, snapshot.amount) > 0):
                raise UserError(_('The source document no longer matches its authorization snapshot. A new approval is required.'))
            authorized_id = self.env.context.get('prv_voucher_payment_id')
            if require_voucher_route and (not authorized_id or str(authorized_id) != str(voucher.id)):
                raise UserError(_(
                    'Pay is blocked from %(bill)s because voucher %(voucher)s is still active. '
                    'Open that voucher and use its Pay button to settle the remaining balance.',
                    bill=move.display_name, voucher=voucher.name))

    def action_create_payment_voucher(self):
        return self._prv_create_voucher('payment')

    def action_create_receive_voucher(self):
        return self._prv_create_voucher('receive')

    def _prv_create_voucher(self, kind):
        if kind == 'payment':
            self.check_access('read')
            self._prv_lock()
            linked_vouchers = self.sudo().mapped('prv_voucher_ids')
            linked_vouchers.invalidate_recordset(['state'])
            blocked = self.sudo().filtered(lambda move:
                move.prv_voucher_ids.filtered(lambda voucher: voucher.state in ACTIVE))
            if blocked:
                details = '; '.join(
                    _('%(bill)s → %(vouchers)s',
                      bill=move.display_name,
                      vouchers=', '.join('%s (%s)' % (voucher.name, voucher.state)
                                         for voucher in move.prv_voucher_ids.filtered(lambda v: v.state in ACTIVE)))
                    for move in blocked
                )
                raise UserError(_(
                    'Cannot create a new Payment Voucher because these bills are linked to active vouchers: %s. '
                    'If a bill was partially paid, use the same voucher to pay its remaining balance. '
                    'Cancel or reject the previous voucher before creating a replacement.', details
                ))
            return {
                'type': 'ir.actions.act_window', 'name': _('Create Payment Voucher'),
                'res_model': 'prv.voucher.create', 'view_mode': 'form',
                'views': [(self.env.ref('payment_receive_voucher.create_payment_voucher_wizard_form').id, 'form')],
                'target': 'new', 'context': {'default_move_ids': [(6, 0, self.ids)]},
            }
        if kind == 'receive':
            self._prv_validate_selection('receive')
            if not self.env['prv.voucher.config'].get_for_voucher(self.company_id, 'receive'):
                raise UserError(_('Create Receive Voucher is unavailable because this company has no active Receive Voucher configuration.'))
        voucher = self.env['prv.voucher'].create({'voucher_type': kind, 'move_ids': [(6, 0, self.ids)]})
        return {'type': 'ir.actions.act_window', 'res_model': 'prv.voucher',
                'view_mode': 'form', 'res_id': voucher.id, 'target': 'current'}

    def action_register_payment(self):
        self._prv_check_payment()
        return super().action_register_payment()

    def action_force_register_payment(self):
        self._prv_check_payment()
        return super().action_force_register_payment()

    def _prv_check_edit(self):
        self._prv_lock()
        linked = self.sudo().mapped('prv_voucher_ids')
        linked.invalidate_recordset(['state'])
        if any(m.sudo().prv_voucher_ids.filtered(lambda voucher: voucher.state in ACTIVE) for m in self):
            raise UserError(_('Cancel the active voucher before modifying or resetting its source documents. Paid vouchers cannot be cancelled.'))

    @api.model_create_multi
    def create(self, vals_list):
        if any(any(k.startswith('prv_') for k in v) for v in vals_list) or self.env.context.get('default_prv_voucher_id'):
            raise AccessError(_('Voucher references are set only by the voucher workflow.'))
        moves = super().create(vals_list)
        moves.filtered('matched_payment_ids')._prv_check_payment()
        return moves

    def write(self, vals):
        if any(k.startswith('prv_') for k in vals):
            raise AccessError(_('Voucher fields are readonly.'))
        if MOVE_LOCK_FIELDS.intersection(vals):
            self._prv_check_edit()
        if 'matched_payment_ids' in vals:
            self._prv_check_payment()
        return super().write(vals)

    def unlink(self):
        self._prv_check_edit()
        return super().unlink()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def action_register_payment(self, ctx=None):
        self.move_id._prv_check_payment()
        return super().action_register_payment(ctx=ctx)

    @api.model_create_multi
    def create(self, vals_list):
        ids = {v.get('move_id') or self.env.context.get('default_move_id') for v in vals_list}
        self.env['account.move'].browse([i for i in ids if i])._prv_check_edit()
        return super().create(vals_list)

    def write(self, vals):
        if LINE_LOCK_FIELDS.intersection(vals):
            moves = self.move_id | self.env['account.move'].browse(vals.get('move_id', []))
            moves._prv_check_edit()
        return super().write(vals)

    def unlink(self):
        self.move_id._prv_check_edit()
        return super().unlink()

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from .policy import required_layers, may_approve

TYPES = [('payment', 'Payment Voucher'), ('receive', 'Receive Voucher')]
STATES = [('draft', 'Draft'), ('waiting', 'Waiting Approval'), ('approved', 'Approved'),
          ('rejected', 'Rejected'), ('cancelled', 'Cancelled')]
ACTIVE = ('draft', 'waiting', 'approved')


class Voucher(models.Model):
    _name = 'prv.voucher'
    _description = 'Payment / Receive Voucher'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(default='New', readonly=True, copy=False, tracking=True)
    voucher_type = fields.Selection(TYPES, required=True, readonly=True, index=True)
    payment_voucher_type_id = fields.Many2one(
        'prv.voucher.payment.type', string='Payment Voucher Type',
        ondelete='restrict', check_company=True, index=True,
    )
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    partner_id = fields.Many2one('res.partner', readonly=True)
    partner_summary = fields.Char(compute='_compute_partner_summary', string='Partner')
    vendor_bank_account = fields.Char(compute='_compute_vendor_bank_info', string='Bank Account Number', store=True, readonly=True)
    vendor_bank_name = fields.Char(compute='_compute_vendor_bank_info', string='Bank Name', store=True, readonly=True)
    vendor_account_holder = fields.Char(compute='_compute_vendor_bank_info', string='Account Holder Name', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', required=True, readonly=True)
    date = fields.Date(default=fields.Date.context_today, required=True, readonly=True)
    state = fields.Selection(STATES, default='draft', readonly=True, tracking=True, index=True, copy=False)
    move_ids = fields.Many2many('account.move', 'prv_voucher_move_rel', 'voucher_id', 'move_id', readonly=True, copy=False)
    bill_ids = fields.One2many('prv.voucher.bill', 'voucher_id', readonly=True)
    detail_ids = fields.One2many('prv.voucher.detail', 'voucher_id', readonly=True)
    tax_ids = fields.One2many('prv.voucher.tax', 'voucher_id', readonly=True)
    step_ids = fields.One2many('prv.voucher.step', 'voucher_id', readonly=True)
    history_ids = fields.One2many('prv.voucher.history', 'voucher_id', readonly=True)
    config_id = fields.Many2one('prv.voucher.config', readonly=True, ondelete='restrict')
    show_pay_button = fields.Boolean(related='config_id.show_pay_button', readonly=True)
    same_partner_required = fields.Boolean(readonly=True)
    bill_count = fields.Integer(compute='_compute_totals')
    amount_total = fields.Monetary(compute='_compute_totals')
    amount_company = fields.Monetary(currency_field='company_currency_id', readonly=True)
    company_currency_id = fields.Many2one(related='company_id.currency_id')
    current_layer = fields.Integer(compute='_compute_current')
    current_approver_id = fields.Many2one('res.users', compute='_compute_current')
    can_decide = fields.Boolean(compute='_compute_current')
    approved_at = fields.Datetime(readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    approved_remarks = fields.Text(readonly=True, copy=False)
    notes = fields.Text(tracking=True)
    settlement_state = fields.Selection([('unpaid', 'Unpaid'), ('partial', 'Partially Paid / In Payment'), ('paid', 'Paid')], compute='_compute_settlement')

    @api.depends('bill_ids.amount')
    def _compute_totals(self):
        for voucher in self:
            voucher.bill_count = len(voucher.bill_ids)
            voucher.amount_total = sum(voucher.bill_ids.mapped('amount'))

    @api.depends('move_ids.partner_id')
    def _compute_partner_summary(self):
        for voucher in self:
            partners = voucher.move_ids.partner_id
            voucher.partner_summary = (partners.display_name if len(partners) == 1
                else _('Multiple Partners (%(count)s)', count=len(partners)))

    @api.depends('move_ids.partner_id', 'move_ids.partner_id.bank_ids',
                 'move_ids.partner_id.bank_ids.acc_number',
                 'move_ids.partner_id.bank_ids.bank_id.name',
                 'move_ids.partner_id.bank_ids.acc_holder_name',
                 'move_ids.partner_id.commercial_partner_id.bank_ids.acc_number',
                 'move_ids.partner_id.commercial_partner_id.bank_ids.bank_id.name',
                 'move_ids.partner_id.commercial_partner_id.bank_ids.acc_holder_name')
    def _compute_vendor_bank_info(self):
        for voucher in self:
            banks = self.env['res.partner.bank']
            for move in voucher.move_ids:
                partner = move.partner_id
                partner_banks = partner.bank_ids.filtered('active')
                if not partner_banks and partner.commercial_partner_id != partner:
                    partner_banks = partner.commercial_partner_id.bank_ids.filtered('active')
                banks |= partner_banks
            voucher.vendor_bank_account = ', '.join(dict.fromkeys(
                bank.acc_number.strip() for bank in banks if bank.acc_number and bank.acc_number.strip()))
            voucher.vendor_bank_name = ', '.join(dict.fromkeys(
                (bank.bank_id.name or bank.bank_name or '').strip()
                for bank in banks if (bank.bank_id.name or bank.bank_name or '').strip()))
            voucher.vendor_account_holder = ', '.join(dict.fromkeys(
                bank.acc_holder_name.strip() for bank in banks
                if bank.acc_holder_name and bank.acc_holder_name.strip()))

    @api.depends('move_ids.payment_state', 'move_ids.amount_residual')
    def _compute_settlement(self):
        for voucher in self:
            states = voucher.move_ids.mapped('payment_state')
            voucher.settlement_state = ('paid' if states and all(s == 'paid' for s in states)
                else 'partial' if any(s in ('paid', 'partial', 'in_payment') for s in states) else 'unpaid')

    @api.depends('state', 'step_ids.state', 'step_ids.approver_id', 'step_ids.delegate_id')
    @api.depends_context('uid')
    def _compute_current(self):
        for voucher in self:
            step = voucher.step_ids.filtered(lambda s: s.state == 'pending')[:1] if voucher.state == 'waiting' else self.env['prv.voucher.step']
            voucher.current_layer = step.sequence if step else 0
            voucher.current_approver_id = step.approver_id if step else False
            voucher.can_decide = bool(step and voucher._allowed(step))

    def _allowed(self, step):
        return self.env.user.has_group('payment_receive_voucher.group_voucher_approver') and may_approve(
            self.env.uid, step.approver_id.id, step.delegate_id.id,
            step.valid_from, step.valid_until, fields.Date.today())

    def _lock(self):
        self.check_access('write')
        self.move_ids._prv_lock()
        if self:
            self.env.cr.execute('SELECT id FROM prv_voucher WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(self.ids)])
        self.invalidate_recordset()
        self.step_ids.invalidate_recordset()

    def _set(self, values):
        # Private method: no RPC/context bypass of workflow-owned fields.
        return super(Voucher, self).write(values)

    def _log(self, action, remarks='', step=None):
        self.ensure_one()
        self.env['prv.voucher.history']._internal_create({
            'voucher_id': self.id, 'action': action, 'remarks': remarks,
            'actor_id': self.env.uid, 'date': fields.Datetime.now(),
            'sequence': step.sequence if step else 0,
            'approver_id': step.approver_id.id if step else False,
            'delegated': bool(step and self.env.uid != step.approver_id.id),
        })
        self.message_post(body=_('%(action)s by %(user)s. %(remarks)s',
                                 action=action, user=self.env.user.display_name, remarks=remarks))

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access('create')
        if not self.env.user.has_group('payment_receive_voucher.group_voucher_user'):
            raise AccessError(_('Voucher User access is required.'))
        result = self.browse()
        for vals in vals_list:
            if set(vals) - {'move_ids', 'voucher_type', 'payment_voucher_type_id', 'notes'}:
                raise AccessError(_('Voucher headers and workflow fields are generated by the system.'))
            commands = vals.get('move_ids', [])
            if len(commands) != 1 or commands[0][0] != 6:
                raise UserError(_('Create vouchers by selecting posted bills/invoices.'))
            moves = self.env['account.move'].browse(commands[0][2]).exists()
            moves.check_access('read')
            moves._prv_lock()
            voucher_type = vals.get('voucher_type')
            payment_type = self.env['prv.voucher.payment.type'].browse(vals.get('payment_voucher_type_id') or []).exists()
            if voucher_type == 'payment' and not payment_type:
                available_types = self.env['prv.voucher.payment.type'].search([
                    ('company_id', '=', moves.company_id.id), ('active', '=', True)], limit=2)
                if len(available_types) == 1:
                    payment_type = available_types
            moves._prv_validate_selection(voucher_type, payment_voucher_type=payment_type)
            if voucher_type == 'payment' and (not payment_type or payment_type.company_id != moves.company_id or not payment_type.active):
                raise UserError(_('Select an active Payment Voucher Type for the same company as the bills.'))
            if voucher_type == 'receive' and payment_type:
                raise UserError(_('Receive Vouchers cannot use a Payment Voucher Type.'))
            config = self.env['prv.voucher.config'].get_for_voucher(moves.company_id, voucher_type, payment_type)
            if voucher_type == 'receive' and not config:
                raise UserError(_('A Receive Voucher requires an active Receive Voucher configuration for the company.'))
            date = fields.Date.context_today(self)
            number = self.env['ir.sequence'].next_by_code('prv.voucher.' + voucher_type, sequence_date=date)
            if not number:
                raise UserError(_('Voucher sequence is missing.'))
            clean = self.with_context({k: v for k, v in self.env.context.items() if not k.startswith('default_')})
            voucher = super(Voucher, clean).create({
                'name': number, 'voucher_type': voucher_type,
                'payment_voucher_type_id': payment_type.id if payment_type else False,
                'company_id': moves.company_id.id,
                'partner_id': moves.partner_id.id if len(moves.partner_id) == 1 else False,
                'currency_id': moves.currency_id.id, 'date': date,
                'same_partner_required': config.require_same_partner if config else True,
                'move_ids': [(6, 0, moves.ids)], 'notes': vals.get('notes', ''), 'state': 'draft',
            })
            # ACLs of account.move remain independent of voucher roles.
            # Selection was read-checked above; only this protected reference is changed.
            moves._prv_set_voucher(voucher)
            voucher._snapshot()
            voucher._log('created')
            result |= voucher
        return result

    def write(self, vals):
        if set(vals) - {'notes', 'payment_voucher_type_id'}:
            raise AccessError(_('Use voucher workflow actions to change this document.'))
        self._lock()
        if any(v.state != 'draft' or (v.create_uid != self.env.user and not self.env.user.has_group('payment_receive_voucher.group_voucher_manager')) for v in self):
            raise AccessError(_('Only the creator or Voucher Manager may edit draft voucher fields.'))
        if 'payment_voucher_type_id' in vals:
            payment_type = self.env['prv.voucher.payment.type'].browse(vals.get('payment_voucher_type_id') or []).exists()
            for voucher in self:
                if voucher.voucher_type != 'payment' and payment_type:
                    raise UserError(_('Receive Vouchers cannot use a Payment Voucher Type.'))
                if payment_type and (payment_type.company_id != voucher.company_id or not payment_type.active):
                    raise UserError(_('Select an active Payment Voucher Type for the same company as the voucher.'))
                config = self.env['prv.voucher.config'].get_for_voucher(
                    voucher.company_id, voucher.voucher_type, payment_type)
                voucher.move_ids._prv_validate_selection(
                    voucher.voucher_type, voucher, payment_type)
                voucher._set({'same_partner_required': config.require_same_partner if config else True})
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Vouchers are audit records. Cancel them instead of deleting.'))

    def copy(self, default=None):
        raise UserError(_('Create a new voucher from the source bills/invoices.'))

    def _snapshot(self):
        self.ensure_one()
        self.bill_ids._internal_unlink()
        self.detail_ids._internal_unlink()
        self.tax_ids._internal_unlink()
        for move in self.move_ids.sorted('id'):
            self.env['prv.voucher.bill']._internal_create({
                'voucher_id': self.id, 'move_id': move.id, 'name': move.name,
                'partner_name': move.partner_id.display_name,
                'invoice_date': move.invoice_date, 'due_date': move.invoice_date_due,
                'amount': move.amount_residual, 'original_total': move.amount_total,
            })
            for line in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
                self.env['prv.voucher.detail']._internal_create({
                    'voucher_id': self.id, 'move_id': move.id, 'source_line_id': line.id,
                    'bill_name': move.name, 'product': line.product_id.display_name or '',
                    'description': line.name, 'account': line.account_id.display_name,
                    'analytic': self._format_analytic_distribution(line), 'quantity': line.quantity,
                    'unit_price': line.price_unit, 'discount': line.discount,
                    'taxes': ', '.join(line.tax_ids.mapped('name')), 'subtotal': line.price_subtotal,
                })
            tax_groups = {}
            for tax_line in move.line_ids.filtered(lambda item: item.tax_line_id):
                tax_name = tax_line.tax_line_id.display_name
                tax_amount = abs(tax_line.balance if move.currency_id == move.company_currency_id else tax_line.amount_currency)
                tax_groups[tax_name] = tax_groups.get(tax_name, 0.0) + tax_amount
            for tax_name, tax_amount in tax_groups.items():
                self.env['prv.voucher.tax']._internal_create({
                    'voucher_id': self.id, 'move_id': move.id, 'tax_name': tax_name, 'amount': tax_amount,
                })

    def _format_analytic_distribution(self, line):
        distribution = line.analytic_distribution or {}
        if not distribution:
            return ''
        account_ids = set()
        for key in distribution:
            account_ids.update(int(value) for value in str(key).split(',') if value.strip().isdigit())
        accounts = self.env['account.analytic.account'].sudo().browse(list(account_ids)).exists()
        names = {account.id: account.display_name for account in accounts}
        parts = []
        for key in distribution:
            account_names = [names.get(int(value), _('Unknown analytic account'))
                             for value in str(key).split(',') if value.strip().isdigit()]
            parts.extend(account_names)
        return ', '.join(dict.fromkeys(parts))

    def _get_print_summary_lines(self):
        self.ensure_one()
        products, taxes = {}, {}
        for detail in self.detail_ids:
            label = detail.product or detail.description or _('Other')
            row = products.setdefault(label, {'kind': 'product', 'label': label, 'quantity': 0.0, 'amount': 0.0})
            row['quantity'] += detail.quantity
            row['amount'] += detail.subtotal
        for tax_line in self.tax_ids:
            taxes[tax_line.tax_name] = taxes.get(tax_line.tax_name, 0.0) + tax_line.amount
        return (sorted(products.values(), key=lambda row: row['label'].casefold()) + [
            {'kind': 'tax', 'label': _('Tax: %s', name), 'quantity': False, 'amount': amount}
            for name, amount in sorted(taxes.items(), key=lambda item: item[0].casefold())
        ])

    def _get_analytic_summary(self):
        self.ensure_one()
        names = []
        for detail in self.detail_ids:
            names.extend(name.strip() for name in (detail.analytic or '').split(',') if name.strip())
        return ', '.join(dict.fromkeys(names))

    def action_submit(self):
        self.ensure_one()
        self._lock()
        if self.state != 'draft':
            raise UserError(_('Only a draft voucher can be submitted.'))
        if self.create_uid != self.env.user and not self.env.user.has_group('payment_receive_voucher.group_voucher_manager'):
            raise AccessError(_('Only the creator or Voucher Manager may submit.'))
        self.move_ids._prv_validate_selection(self.voucher_type, self, self.payment_voucher_type_id)
        config = self.env['prv.voucher.config'].get_for_voucher(
            self.company_id, self.voucher_type, self.payment_voucher_type_id)
        if config:
            config.layer_ids._check_layer()
        if config and config.layer_ids and not any(l.min_amount == 0 for l in config.layer_ids):
            raise UserError(_('Configure at least one zero-threshold approval layer.'))
        self._snapshot()
        amount = self.currency_id._convert(self.amount_total, self.company_currency_id, self.company_id, self.date)
        if not config or not config.layer_ids:
            auto_reason = (_('No active approval configuration applies; approved automatically on submission.')
                           if not config else _('No approval layers are configured; approved automatically on submission.'))
            self._set({
                'config_id': config.id if config else False,
                'amount_company': amount,
                'same_partner_required': config.require_same_partner if config else self.same_partner_required,
                'state': 'approved', 'approved_at': fields.Datetime.now(),
                'approved_by_id': self.env.uid, 'approved_remarks': auto_reason,
            })
            self._log('submitted')
            self._log('auto-approved', auto_reason)
            return True
        layers = required_layers(config.layer_ids, amount)
        for layer in layers:
            self.env['prv.voucher.step']._internal_create({
                'voucher_id': self.id, 'sequence': layer.sequence,
                'approver_id': layer.approver_id.id, 'delegate_id': layer.delegate_id.id,
                'valid_from': layer.valid_from, 'valid_until': layer.valid_until,
            })
        self._set({'config_id': config.id, 'amount_company': amount, 'state': 'waiting',
                   'same_partner_required': config.require_same_partner})
        self._log('submitted')
        return True

    def _action_decision(self, decision):
        self.ensure_one()
        self.check_access('read')
        if decision not in ('approve', 'reject'):
            raise UserError(_('Invalid decision.'))
        title = _('Approve Voucher') if decision == 'approve' else _('Reject Voucher')
        return {'type': 'ir.actions.act_window', 'name': title,
                'res_model': 'prv.voucher.decision', 'view_mode': 'form', 'target': 'new',
                'context': {'default_voucher_id': self.id, 'default_decision': decision}}

    def action_approve(self):
        return self._action_decision('approve')

    def action_reject(self):
        return self._action_decision('reject')

    def _decision(self, decision, remarks):
        self.ensure_one()
        self._lock()
        step = self.step_ids.filtered(lambda s: s.state == 'pending')[:1]
        if self.state != 'waiting' or not step or not self._allowed(step):
            raise AccessError(_('Only the current layer approver or a currently valid delegate may decide.'))
        if decision not in ('approve', 'reject'):
            raise UserError(_('Invalid decision.'))
        if decision == 'reject' and not remarks.strip():
            raise UserError(_('A rejection reason is required.'))
        step._internal_write({'state': 'approved' if decision == 'approve' else 'rejected',
                              'actor_id': self.env.uid, 'acted_at': fields.Datetime.now(), 'remarks': remarks})
        self._log(decision, remarks, step)
        if decision == 'reject':
            self._set({'state': 'rejected'})
        elif not self.step_ids.filtered(lambda s: s.state == 'pending'):
            self._set({'state': 'approved', 'approved_at': fields.Datetime.now(),
                       'approved_by_id': self.env.uid, 'approved_remarks': remarks})
        return True

    def action_cancel(self):
        self.ensure_one()
        self._lock()
        manager = self.env.user.has_group('payment_receive_voucher.group_voucher_manager')
        if self.state not in ACTIVE or not (manager or (self.state == 'draft' and self.create_uid == self.env.user)):
            raise AccessError(_('Only a Voucher Manager may cancel a submitted voucher; creators may cancel their drafts.'))
        if self.state == 'approved' and any(
                b.move_id.payment_state in ('in_payment', 'paid')
                or b.currency_id.compare_amounts(b.move_id.amount_residual, b.amount) != 0
                for b in self.bill_ids):
            raise UserError(_('An approved voucher with payment activity cannot be cancelled.'))
        self._set({'state': 'cancelled'})
        self.move_ids._prv_clear_voucher(self)
        self._log('cancelled')
        return True

    def action_pay(self):
        """Open Odoo's native payment registration wizard for outstanding documents."""
        self.ensure_one()
        self.check_access('read')
        if self.state != 'approved':
            raise UserError(_('Only an approved voucher can open payment registration.'))
        if not self.config_id.sudo().show_pay_button:
            raise AccessError(_('The Pay button is disabled in this voucher approval configuration.'))
        if any(move.sudo().prv_voucher_id != self for move in self.move_ids):
            raise UserError(_('A newer voucher is linked to one or more source documents. Open and pay from the latest voucher.'))
        if not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(_('Accounting payment access is required.'))
        payable = self.move_ids.filtered(
            lambda move: move.state == 'posted'
            and move.amount_residual > 0
            and move.payment_state not in ('paid', 'in_payment', 'reversed', 'blocked')
        )
        if not payable:
            raise UserError(_('There are no outstanding documents available for payment registration.'))
        payable._prv_check_payment()
        return payable.action_register_payment()


class ImmutableVoucherChild(models.AbstractModel):
    _name = 'prv.voucher.immutable'
    _description = 'Immutable Voucher Audit Data'

    voucher_id = fields.Many2one('prv.voucher', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='voucher_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='voucher_id.currency_id')

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Voucher audit data can only be generated by workflow actions.'))

    def write(self, vals):
        raise AccessError(_('Voucher audit data is readonly.'))

    def unlink(self):
        raise AccessError(_('Voucher audit data cannot be deleted.'))

    @api.model
    def _internal_create(self, vals):
        clean = self.sudo().with_context({k: v for k, v in self.env.context.items() if not k.startswith('default_')})
        return super(ImmutableVoucherChild, clean).create(vals)

    def _internal_write(self, vals):
        return super(ImmutableVoucherChild, self.sudo()).write(vals)

    def _internal_unlink(self):
        return super(ImmutableVoucherChild, self.sudo()).unlink()


class VoucherBill(models.Model):
    _name = 'prv.voucher.bill'
    _inherit = 'prv.voucher.immutable'
    _description = 'Voucher Bill Summary Snapshot'
    _order = 'id'
    move_id = fields.Many2one('account.move', required=True, ondelete='restrict')
    name = fields.Char()
    partner_name = fields.Char(string='Partner')
    invoice_date = fields.Date()
    due_date = fields.Date()
    original_total = fields.Monetary()
    amount = fields.Monetary(string='Authorized Amount')
    current_due = fields.Monetary(related='move_id.amount_residual')


class VoucherDetail(models.Model):
    _name = 'prv.voucher.detail'
    _inherit = 'prv.voucher.immutable'
    _description = 'Flattened Bill Detail Snapshot'
    _order = 'id'
    move_id = fields.Many2one('account.move', ondelete='restrict')
    source_line_id = fields.Many2one('account.move.line', ondelete='set null')
    bill_name = fields.Char()
    product = fields.Char()
    description = fields.Text()
    account = fields.Char()
    analytic = fields.Char(string='Analytic Distribution')
    quantity = fields.Float()
    unit_price = fields.Monetary()
    discount = fields.Float()
    taxes = fields.Char()
    subtotal = fields.Monetary()


class VoucherTax(models.Model):
    _name = 'prv.voucher.tax'
    _inherit = 'prv.voucher.immutable'
    _description = 'Voucher Tax Snapshot'
    _order = 'tax_name, id'

    move_id = fields.Many2one('account.move', ondelete='restrict')
    tax_name = fields.Char(required=True)
    currency_id = fields.Many2one(related='voucher_id.currency_id')
    amount = fields.Monetary(currency_field='currency_id', required=True)


class VoucherStep(models.Model):
    _name = 'prv.voucher.step'
    _inherit = 'prv.voucher.immutable'
    _description = 'Voucher Approval Route Snapshot'
    _order = 'sequence, id'
    sequence = fields.Integer(string='Layer')
    approver_id = fields.Many2one('res.users', ondelete='restrict')
    delegate_id = fields.Many2one('res.users', ondelete='restrict')
    valid_from = fields.Date()
    valid_until = fields.Date()
    state = fields.Selection([('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending')
    actor_id = fields.Many2one('res.users', ondelete='restrict')
    acted_at = fields.Datetime()
    remarks = fields.Text()


class VoucherHistory(models.Model):
    _name = 'prv.voucher.history'
    _inherit = 'prv.voucher.immutable'
    _description = 'Voucher Approval History'
    _order = 'id'
    sequence = fields.Integer(string='Layer')
    approver_id = fields.Many2one('res.users', ondelete='restrict')
    actor_id = fields.Many2one('res.users', required=True, ondelete='restrict')
    date = fields.Datetime(required=True)
    action = fields.Char(required=True)
    delegated = fields.Boolean()
    remarks = fields.Text()

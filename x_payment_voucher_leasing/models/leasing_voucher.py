# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from .policy import required_layers, may_approve

STATES = [
    ('draft', 'Draft'),
    ('waiting', 'Waiting Approval'),
    ('approved', 'Approved'),
    ('paid', 'Paid'),
    ('rejected', 'Rejected'),
    ('cancelled', 'Cancelled')
]
ACTIVE_STATES = ('draft', 'waiting', 'approved')


class LeasingPaymentVoucher(models.Model):
    _name = 'leasing.payment.voucher'
    _description = 'Leasing Payment Voucher'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(string='Voucher Number', default='New', readonly=True, copy=False, tracking=True)
    voucher_type = fields.Char(string='Voucher Type', default='Payment Voucher Leasing', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, default=lambda s: s.env.company)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, default=lambda s: s.env.company.currency_id)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    partner_summary = fields.Char(string='Vendor / Partner', compute='_compute_partner_summary', store=True)
    date = fields.Date(string='Date', default=fields.Date.context_today, required=True, readonly=True)

    state = fields.Selection(STATES, default='draft', readonly=True, tracking=True, index=True, copy=False)
    settlement_state = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid')
    ], string='Settlement State', default='unpaid', readonly=True, tracking=True, copy=False)

    line_ids = fields.One2many('leasing.payment.voucher.line', 'voucher_id', string='Daftar Leasing Terpilih', readonly=True)
    step_ids = fields.One2many('leasing.payment.voucher.step', 'voucher_id', string='Approval Steps', readonly=True)
    history_ids = fields.One2many('leasing.payment.voucher.history', 'voucher_id', string='Approval History', readonly=True)

    config_id = fields.Many2one('leasing.voucher.config', string='Approval Configuration', readonly=True, ondelete='restrict')
    same_partner_required = fields.Boolean(readonly=True)

    installment_count = fields.Integer(string='Installment Count', compute='_compute_totals', store=True)
    amount_principal = fields.Monetary(string='Total Pokok', compute='_compute_totals', store=True, currency_field='currency_id')
    amount_interest = fields.Monetary(string='Total Bunga', compute='_compute_totals', store=True, currency_field='currency_id')
    amount_total = fields.Monetary(string='Amount Total', compute='_compute_totals', store=True, currency_field='currency_id', tracking=True)

    current_layer = fields.Integer(string='Current Layer', compute='_compute_current')
    current_approver_id = fields.Many2one('res.users', string='Current Approver', compute='_compute_current')
    can_decide = fields.Boolean(compute='_compute_current')
    can_reset = fields.Boolean(compute='_compute_can_reset')

    approved_at = fields.Datetime(string='Approved At', readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)
    approved_remarks = fields.Text(string='Approval Remarks', readonly=True, copy=False)
    notes = fields.Text(string='Notes', tracking=True)

    @api.depends('line_ids.principal', 'line_ids.interest', 'line_ids.total')
    def _compute_totals(self):
        for voucher in self:
            voucher.installment_count = len(voucher.line_ids)
            voucher.amount_principal = sum(voucher.line_ids.mapped('principal'))
            voucher.amount_interest = sum(voucher.line_ids.mapped('interest'))
            voucher.amount_total = sum(voucher.line_ids.mapped('total'))

    @api.depends('line_ids.vendor_id')
    def _compute_partner_summary(self):
        for voucher in self:
            vendors = voucher.line_ids.mapped('vendor_id')
            if len(vendors) == 1:
                voucher.partner_summary = vendors.display_name
            elif len(vendors) > 1:
                voucher.partner_summary = _('Multiple Vendors (%s)', len(vendors))
            else:
                voucher.partner_summary = voucher.partner_id.display_name if voucher.partner_id else '-'

    @api.depends('state', 'step_ids.state', 'step_ids.approver_id', 'step_ids.delegate_id')
    @api.depends_context('uid')
    def _compute_current(self):
        for voucher in self:
            step = voucher.step_ids.filtered(lambda s: s.state == 'pending')[:1] if voucher.state == 'waiting' else self.env['leasing.payment.voucher.step']
            voucher.current_layer = step.sequence if step else 0
            voucher.current_approver_id = step.approver_id if step else False
            voucher.can_decide = bool(step and voucher._allowed(step))

    @api.depends('state', 'create_uid', 'settlement_state')
    @api.depends_context('uid')
    def _compute_can_reset(self):
        manager = self.env.user.has_group('x_payment_voucher_leasing.group_leasing_voucher_manager')
        for voucher in self:
            permitted = manager or (voucher.create_uid == self.env.user and voucher.state in ('draft', 'waiting'))
            has_paid = voucher.settlement_state == 'paid' or voucher.state == 'paid'
            voucher.can_reset = voucher.state in ACTIVE_STATES and permitted and not has_paid

    def _allowed(self, step):
        return (
            self.env.is_superuser()
            or (
                self.env.user.has_group('x_payment_voucher_leasing.group_leasing_voucher_approver')
                and may_approve(
                    self.env.uid,
                    step.approver_id.id,
                    step.delegate_id.id if step.delegate_id else False,
                    step.valid_from,
                    step.valid_until,
                    fields.Date.today()
                )
            )
        )

    def _log(self, action, remarks='', step=None):
        self.ensure_one()
        self.env['leasing.payment.voucher.history'].create({
            'voucher_id': self.id,
            'action': action,
            'remarks': remarks or '',
            'actor_id': self.env.uid,
            'date': fields.Datetime.now(),
            'sequence': step.sequence if step else 0,
            'approver_id': step.approver_id.id if step else False,
            'delegated': bool(step and self.env.uid != step.approver_id.id),
        })
        self.message_post(body=_(
            "%(action)s oleh %(user)s. %(remarks)s",
            action=action.capitalize(),
            user=self.env.user.display_name,
            remarks=f"Catatan: {remarks}" if remarks else ""
        ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                date = vals.get('date') or fields.Date.context_today(self)
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'leasing.payment.voucher', sequence_date=date
                ) or 'New'
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) - {'notes'}:
            # allow system actions/methods
            pass
        return super().write(vals)

    def action_submit(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Hanya voucher draft yang dapat diajukan (submit).'))
        if not self.line_ids:
            raise UserError(_('Voucher belum memiliki daftar angsuran leasing terpilih.'))

        config = self.env['leasing.voucher.config'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('active', '=', True)
        ], limit=1)

        if not config:
            raise UserError(_(
                'Belum ada konfigurasi approval yang aktif untuk perusahaan %s. '
                'Silakan hubungi administrator untuk mengatur Leasing Voucher Approval Policy.',
                self.company_id.name
            ))

        config.layer_ids._check_layer()
        if not config.layer_ids:
            raise UserError(_('Konfigurasi approval belum memiliki layer persetujuan.'))

        # Check threshold
        layers = required_layers(config.layer_ids, self.amount_total)
        if not layers:
            raise UserError(_('Tidak ada layer approval yang sesuai dengan nominal total voucher (minimal harus ada layer dengan threshold 0).'))

        # Clear existing steps and generate frozen snapshot of route
        self.step_ids.unlink()
        for layer in layers:
            self.env['leasing.payment.voucher.step'].create({
                'voucher_id': self.id,
                'sequence': layer.sequence,
                'approver_id': layer.approver_id.id,
                'delegate_id': layer.delegate_id.id if layer.delegate_id else False,
                'valid_from': layer.valid_from,
                'valid_until': layer.valid_until,
                'state': 'pending',
            })

        self.write({
            'config_id': config.id,
            'state': 'waiting',
            'same_partner_required': config.require_same_partner,
        })
        self._log('submitted')
        return True

    def _action_decision(self, decision):
        self.ensure_one()
        title = _('Approve Payment Voucher Leasing') if decision == 'approve' else _('Reject Payment Voucher Leasing')
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'leasing.voucher.decision',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_voucher_id': self.id,
                'default_decision': decision,
            }
        }

    def action_approve(self):
        return self._action_decision('approve')

    def action_reject(self):
        return self._action_decision('reject')

    def _decision(self, decision, remarks):
        self.ensure_one()
        step = self.step_ids.filtered(lambda s: s.state == 'pending')[:1]
        if self.state != 'waiting' or not step or not self._allowed(step):
            raise AccessError(_('Hanya approver layer saat ini atau delegasi aktif yang berhak memberikan keputusan.'))
        if decision not in ('approve', 'reject'):
            raise UserError(_('Keputusan tidak valid.'))
        if decision == 'reject' and not remarks.strip():
            raise UserError(_('Alasan penolakan (remarks) wajib diisi jika menolak voucher.'))

        step.write({
            'state': 'approved' if decision == 'approve' else 'rejected',
            'actor_id': self.env.uid,
            'acted_at': fields.Datetime.now(),
            'remarks': remarks or '',
        })
        self._log(decision, remarks, step)

        if decision == 'reject':
            self.write({'state': 'rejected'})
        else:
            # Check if there are remaining pending steps
            pending_steps = self.step_ids.filtered(lambda s: s.state == 'pending')
            if not pending_steps:
                self.write({
                    'state': 'approved',
                    'approved_at': fields.Datetime.now(),
                    'approved_by_id': self.env.uid,
                    'approved_remarks': remarks or '',
                })
        return True

    def action_cancel(self):
        self.ensure_one()
        if self.state == 'paid' or self.settlement_state == 'paid':
            raise UserError(_('Voucher yang sudah terbayar tidak dapat dibatalkan.'))
        # Release loan lines
        loan_lines = self.line_ids.mapped('loan_line_id')
        if loan_lines:
            loan_lines.write({'leasing_voucher_id': False})
        self.write({'state': 'cancelled'})
        self._log('cancelled')
        return True

    def action_reset(self):
        """Reset voucher and release loan lines."""
        self.ensure_one()
        if self.state == 'paid' or self.settlement_state == 'paid':
            raise UserError(_('Voucher yang sudah terbayar tidak dapat di-reset.'))
        loan_lines = self.line_ids.mapped('loan_line_id')
        if loan_lines:
            loan_lines.write({'leasing_voucher_id': False})
        self.write({'state': 'draft'})
        self.step_ids.unlink()
        self._log('reset to draft')
        return True

    def action_open_pay_wizard(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Pembayaran angsuran hanya dapat diproses untuk voucher yang berstatus Approved.'))
        if self.settlement_state == 'paid':
            raise UserError(_('Voucher ini sudah terbayar (settled).'))

        return {
            'name': _('Pay Installments'),
            'type': 'ir.actions.act_window',
            'res_model': 'leasing.voucher.pay.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_voucher_id': self.id,
                'default_payment_date': fields.Date.context_today(self),
            }
        }

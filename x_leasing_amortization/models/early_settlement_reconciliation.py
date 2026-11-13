import json
from collections import defaultdict

from odoo import Command, api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import SQL


_CREATE_TOKEN = object()


class AccountAccount(models.Model):
    _inherit = 'account.account'

    is_early_settlement_clearing = fields.Boolean(string='Pelunasan Dipercepat')
    early_settlement_target_account_id = fields.Many2one(
        'account.account', string='Akun Target', company_dependent=True,
        help='Akun debit Hutang Bank/Leasing untuk Recon Clearing AP Leasing pada company aktif.',
    )
    early_settlement_journal_id = fields.Many2one(
        'account.journal', string='Journal', company_dependent=True,
        domain=lambda self: [('company_id', '=', self.env.company.id), ('type', '=', 'general')],
        help='Jurnal umum untuk Recon Clearing AP Leasing pada company aktif.',
    )


class AccountMove(models.Model):
    _inherit = 'account.move'

    is_early_settlement = fields.Boolean(string='Pelunasan Dipercepat', copy=False, tracking=True)
    early_settlement_recon_move_ids = fields.One2many(
        'account.move', 'early_settlement_recon_bill_id', string='Recon Clearing AP Leasing',
        readonly=True, copy=False,
    )
    early_settlement_recon_bill_id = fields.Many2one(
        'account.move', string='Vendor Bill Pelunasan Dipercepat',
        readonly=True, copy=False, check_company=True, index=True, ondelete='restrict',
    )
    early_settlement_recon_count = fields.Integer(compute='_compute_early_settlement_recon_count')

    @api.depends('early_settlement_recon_move_ids')
    def _compute_early_settlement_recon_count(self):
        for bill in self:
            bill.early_settlement_recon_count = len(bill.early_settlement_recon_move_ids)

    @api.model_create_multi
    def create(self, values_list):
        prepared = []
        for values in values_list:
            values = dict(values)
            if values.get('early_settlement_loan_id', self.env.context.get('default_early_settlement_loan_id')):
                values['is_early_settlement'] = True
            if (values.get('early_settlement_recon_bill_id', self.env.context.get('default_early_settlement_recon_bill_id'))
                    and self.env.context.get('_early_settlement_recon_token') is not _CREATE_TOKEN):
                raise UserError(_('Gunakan tombol Recon Clearing AP Leasing pada Vendor Bill untuk membuat jurnal terkait.'))
            prepared.append(values)
        return super().create(prepared)

    def _active_early_settlement_recon_moves(self):
        self.ensure_one()
        return self.early_settlement_recon_move_ids.filtered(
            lambda move: move.state != 'cancel'
            and not move._fully_reversed_early_settlement_recon())

    def _fully_reversed_early_settlement_recon(self):
        self.ensure_one()
        reversals = self.reversal_move_ids.filtered(lambda move: move.state == 'posted')
        if not reversals:
            return False
        # A posted partial/edited reversal does not neutralize the original
        # journal. Treat it as active, otherwise retrying can double-clear it.
        lines = self.line_ids | reversals.line_ids
        for account in lines.account_id:
            items = lines.filtered(lambda line: line.account_id == account)
            if not self.company_currency_id.is_zero(sum(items.mapped('balance'))):
                return False
            for currency in items.currency_id:
                if not currency.is_zero(sum(items.filtered(
                        lambda line: line.currency_id == currency).mapped('amount_currency'))):
                    return False
        return True

    def write(self, values):
        if 'early_settlement_recon_bill_id' in values and any(
                move.early_settlement_recon_bill_id.id != (values['early_settlement_recon_bill_id'] or False)
                for move in self):
            raise UserError(_('Link jurnal Recon Clearing ke Vendor Bill tidak dapat diubah.'))
        if values.get('early_settlement_loan_id'):
            values = dict(values, is_early_settlement=True)
        if values.get('is_early_settlement') is False and any(
                move.early_settlement_loan_id or move._active_early_settlement_recon_moves() for move in self):
            raise UserError(_('Penanda Pelunasan Dipercepat tidak dapat dilepas dari bill yang terhubung leasing/jurnal Recon aktif.'))
        return super().write(values)

    @api.constrains('is_early_settlement', 'move_type')
    def _check_early_settlement_marker(self):
        if any(move.is_early_settlement and move.move_type != 'in_invoice' for move in self):
            raise ValidationError(_('Penanda Pelunasan Dipercepat hanya untuk Vendor Bill.'))

    def _check_recon_before_bill_reset(self):
        for bill in self:
            if bill._active_early_settlement_recon_moves():
                raise UserError(_(
                    'Review dan batalkan/balikkan jurnal Recon Clearing AP Leasing aktif '
                    'sebelum membatalkan atau mengembalikan Vendor Bill ke Draft.'))

    def button_draft(self):
        self._check_recon_before_bill_reset()
        return super().button_draft()

    def button_cancel(self):
        self._check_recon_before_bill_reset()
        return super().button_cancel()

    def _early_settlement_recon_action(self, moves):
        moves.check_access('read')
        action = {
            'type': 'ir.actions.act_window', 'name': _('Recon Clearing AP Leasing'),
            'res_model': 'account.move', 'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)], 'context': {'default_move_type': 'entry'},
        }
        if len(moves) == 1:
            action.update(view_mode='form', res_id=moves.id,
                          views=[(self.env.ref('account.view_move_form').id, 'form')])
        return action

    def action_view_early_settlement_recon(self):
        self.ensure_one()
        self.check_access('read')
        return self._early_settlement_recon_action(self.early_settlement_recon_move_ids)

    def _early_settlement_clearing_lines(self):
        self.ensure_one()
        # Only invoice-item clearing balances, never payable, tax, penalty or
        # interest on other accounts. Use native residuals, not bill totals.
        return self.line_ids.filtered(
            lambda line: line.display_type == 'product' and not line.tax_line_id
            and line.account_id.is_early_settlement_clearing and not line.reconciled)

    def _prepare_early_settlement_recon(self, lines):
        self.ensure_one()
        bill = self.with_company(self.company_id)
        buckets = defaultdict(lambda: self.env['account.move.line'])
        settings = {}
        for line in lines:
            account = line.account_id.with_company(bill.company_id)
            target = account.early_settlement_target_account_id
            journal = account.early_settlement_journal_id
            if not target or not journal:
                raise UserError(_('Lengkapi Akun Target dan Journal Pelunasan Dipercepat pada CoA %s.', account.display_name))
            if (not account.active or not account.reconcile
                    or account.account_type in ('asset_receivable', 'liability_payable', 'off_balance')):
                raise UserError(_('Akun Clearing %s harus aktif, Allow Reconciliation, dan bukan Receivable/Payable/Off-Balance.', account.display_name))
            # TEMPORARY: validasi Akun Target dinonaktifkan sementara atas permintaan user.
            # Aktifkan kembali setelah konfigurasi Akun Target di CoA diperbaiki.
            # if (target == account or target.is_early_settlement_clearing or not target.active
            #         or target.account_type in ('asset_receivable', 'liability_payable', 'off_balance')):
            #     raise UserError(_('Akun Target harus aktif, berbeda dari akun Clearing, dan merupakan akun buku besar Hutang Bank/Leasing.'))
            if any(not item.filtered_domain(item._check_company_domain(bill.company_id)) for item in (account, target)):
                raise UserError(_('Akun Clearing dan Akun Target harus tersedia pada company Vendor Bill.'))
            if journal.company_id != bill.company_id or journal.type != 'general' or not journal.active:
                raise UserError(_('Journal Recon harus jurnal umum aktif pada company Vendor Bill.'))
            if ((journal.currency_id and journal.currency_id != bill.currency_id)
                    or any(item.currency_id and item.currency_id != bill.currency_id for item in (account, target))
                    or line.currency_id != bill.currency_id):
                raise UserError(_('Mata uang jurnal/akun Recon harus sesuai dengan Vendor Bill.'))
            key = (account.id, journal.id, target.id, json.dumps(line.analytic_distribution or {}, sort_keys=True))
            buckets[key] |= line
            settings[key] = (account, journal, target, line.analytic_distribution or {})

        grouped = {}
        for key, source in buckets.items():
            account, journal, target, analytic = settings[key]
            balance = bill.company_currency_id.round(sum(source.mapped('amount_residual')))
            foreign = bill.currency_id.round(sum(source.mapped('amount_residual_currency')))
            if balance <= 0 or foreign <= 0:
                raise UserError(_('Saldo Clearing yang direkonsiliasi harus berupa saldo debit positif. Review akun %s.', account.display_name))
            values = grouped.setdefault(journal.id, {
                'move_type': 'entry', 'journal_id': journal.id, 'company_id': bill.company_id.id,
                'currency_id': bill.currency_id.id, 'partner_id': bill.partner_id.id,
                'date': bill.date, 'auto_post': 'no',
                'ref': _('Recon Clearing AP Leasing - %s', bill.name),
                'early_settlement_recon_bill_id': bill.id, 'line_ids': [],
            })
            for item, sign in ((target, 1), (account, -1)):
                values['line_ids'].append(Command.create({
                    'name': _('Recon Clearing AP Leasing - %s', bill.name),
                    'account_id': item.id, 'partner_id': bill.partner_id.id,
                    'debit': balance if sign > 0 else 0, 'credit': balance if sign < 0 else 0,
                    'currency_id': bill.currency_id.id, 'amount_currency': sign * foreign,
                    'analytic_distribution': analytic, 'tax_ids': [Command.clear()],
                }))
        return list(grouped.values())

    def _reconcile_early_settlement_lines(self, sources, moves):
        self.ensure_one()
        for account in sources.account_id:
            originals = sources.filtered(lambda line: line.account_id == account)
            credits = moves.line_ids.filtered(lambda line: line.account_id == account and not line.reconciled)
            combined = originals | credits
            if (not credits or not self.company_currency_id.is_zero(sum(combined.mapped('amount_residual')))
                    or not self.currency_id.is_zero(sum(combined.mapped('amount_residual_currency')))):
                raise UserError(_('Saldo jurnal Recon yang sudah ada berbeda. Review jurnal terkait; jurnal baru tidak dibuat untuk menghindari duplikasi.'))
            combined.reconcile()
            if not all(originals.mapped('reconciled')):
                raise UserError(_('Rekonsiliasi Clearing belum lengkap. Review pengaturan mata uang/akun.'))

    def action_recon_clearing_ap_leasing(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(_('Hanya user Accounting/Invoicing yang dapat memproses Recon Clearing AP Leasing.'))
        self.check_access('write')
        self.env['account.move'].check_access('create')
        if self.company_id not in self.env.companies:
            raise AccessError(_('Aktifkan company Vendor Bill sebelum memproses Recon Clearing.'))
        with self.env.cr.savepoint():
            self.flush_recordset()
            self.env.cr.execute(SQL('SELECT id FROM account_move WHERE id = %s FOR UPDATE', self.id))
            # Bump the row version even on retry paths so simultaneous clicks
            # use Odoo's transaction retry instead of a stale MVCC snapshot.
            self.env.cr.execute(SQL('UPDATE account_move SET write_date = write_date WHERE id = %s', self.id))
            self.invalidate_recordset()
            self.line_ids.invalidate_recordset()
            if self.move_type != 'in_invoice' or self.state != 'posted' or not self.is_early_settlement:
                raise UserError(_('Recon Clearing AP Leasing hanya untuk Vendor Bill Pelunasan Dipercepat yang sudah Posted.'))
            active = self._active_early_settlement_recon_moves()
            if any(move.state != 'posted' for move in active):
                # Native Reset to Draft can retain general-ledger matching.
                # Do not report a Draft journal as a completed reconciliation.
                raise UserError(_('Jurnal Recon terkait masih Draft. Review/batalkan jurnal tersebut sebelum memproses ulang.'))
            sources = self._early_settlement_clearing_lines()
            if not sources:
                if active:
                    return self._early_settlement_recon_action(active)
                raise UserError(_('Tidak ada sisa saldo baris Clearing AP Leasing yang ditandai Pelunasan Dipercepat untuk direkonsiliasi.'))
            if active:
                self._reconcile_early_settlement_lines(sources, active)
                return self._early_settlement_recon_action(active)
            prepared = self._prepare_early_settlement_recon(sources)
            moves = self.env['account.move'].with_company(self.company_id).with_context(
                _early_settlement_recon_token=_CREATE_TOKEN).create(prepared)
            moves.action_post()
            if any(move.date != self.date or move.state != 'posted' for move in moves):
                raise UserError(_('Jurnal Recon harus Posted pada Accounting Date Vendor Bill. Review periode terkunci; tanggal tidak digeser otomatis.'))
            self._reconcile_early_settlement_lines(sources, moves)
            self.message_post(body=_('Recon Clearing AP Leasing selesai: %s. Rekonsiliasi ini bukan pembayaran vendor.', ', '.join(moves.mapped('name'))))
            return self._early_settlement_recon_action(moves)


class AccountLoanLine(models.Model):
    _inherit = 'account.loan.line'

    early_settlement_state = fields.Selection(
        [('posted', 'Posted')], string='Pelunasan Dipercepat',
        compute='_compute_early_settlement_state', compute_sudo=True,
        readonly=True, copy=False,
        help='Posted jika baris angsuran pada bill pelunasan sudah direkonsiliasi '
             'dengan jurnal Recon Clearing AP Leasing yang Posted dan belum dibalik penuh. '
             'Ini bukan status pembayaran vendor atau jurnal angsuran rutin.',
    )

    @api.depends(
        'loan_id', 'company_id',
        'early_settlement_invoice_line_ids.reconciled',
        'early_settlement_invoice_line_ids.display_type',
        'early_settlement_invoice_line_ids.tax_line_id',
        'early_settlement_invoice_line_ids.move_id.state',
        'early_settlement_invoice_line_ids.move_id.company_id',
        'early_settlement_invoice_line_ids.move_id.is_early_settlement',
        'early_settlement_invoice_line_ids.move_id.early_settlement_loan_id',
        'early_settlement_invoice_line_ids.matched_credit_ids.credit_move_id.move_id.state',
        'early_settlement_invoice_line_ids.matched_credit_ids.credit_move_id.move_id.early_settlement_recon_bill_id',
        'early_settlement_invoice_line_ids.move_id.early_settlement_recon_move_ids.state',
        'early_settlement_invoice_line_ids.move_id.early_settlement_recon_move_ids.line_ids.balance',
        'early_settlement_invoice_line_ids.move_id.early_settlement_recon_move_ids.line_ids.amount_currency',
        'early_settlement_invoice_line_ids.move_id.early_settlement_recon_move_ids.line_ids.account_id',
        'early_settlement_invoice_line_ids.move_id.early_settlement_recon_move_ids.line_ids.currency_id',
        'early_settlement_invoice_line_ids.move_id.early_settlement_recon_move_ids.reversal_move_ids.state',
        'early_settlement_invoice_line_ids.move_id.early_settlement_recon_move_ids.reversal_move_ids.line_ids.balance',
        'early_settlement_invoice_line_ids.move_id.early_settlement_recon_move_ids.reversal_move_ids.line_ids.amount_currency',
        'early_settlement_invoice_line_ids.move_id.early_settlement_recon_move_ids.reversal_move_ids.line_ids.account_id',
        'early_settlement_invoice_line_ids.move_id.early_settlement_recon_move_ids.reversal_move_ids.line_ids.currency_id',
    )
    def _compute_early_settlement_state(self):
        """Derived audit badge, never a substitute for a regular payment move.

        Nonstored so existing reconciliations work immediately after upgrade.
        Sudo computes only this status for an already-readable schedule line
        (including Fleet readers); no journal/partner details are exposed.
        Require the actual native match to this bill's active posted Recon,
        not just a Paid bill or a zero Clearing residual matched elsewhere.
        """
        sources = self.early_settlement_invoice_line_ids.filtered(
            lambda source: source.display_type == 'product' and not source.tax_line_id
            and source.move_id.state == 'posted' and source.move_id.is_early_settlement
            and source.move_id.early_settlement_loan_id == source.early_settlement_schedule_line_id.loan_id
            and source.move_id.company_id == source.early_settlement_schedule_line_id.company_id)
        recons = {
            bill.id: bill._active_early_settlement_recon_moves().filtered(lambda move: move.state == 'posted')
            for bill in sources.move_id
        }
        groups = defaultdict(lambda: self.env['account.move.line'])
        for source in sources:
            groups[(source.early_settlement_schedule_line_id.id, source.move_id.id)] |= source
        completed = set()
        for (line_id, bill_id), items in groups.items():
            if recons[bill_id] and all(
                    item.reconciled and any(
                        match.credit_move_id.move_id in recons[bill_id]
                        for match in item.matched_credit_ids)
                    for item in items):
                completed.add(line_id)
        for line in self:
            line.early_settlement_state = 'posted' if line.id in completed else False

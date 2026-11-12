from math import isfinite

from odoo import Command, api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL


_CREATE_TOKEN = object()
_SETTINGS = {'clearing_journal_id', 'clearing_account_id',
             'clearing_first_installment_account_id', 'clearing_down_payment_account_id'}


class AccountLoan(models.Model):
    _inherit = 'account.loan'

    clearing_journal_id = fields.Many2one(
        'account.journal', string='Jurnal Clearing AP Leasing', check_company=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]", copy=True,
    )
    clearing_account_id = fields.Many2one(
        'account.account', string='Akun Clearing AP Leasing', check_company=True, copy=True,
    )
    clearing_first_installment_account_id = fields.Many2one(
        'account.account', string='Akun AP Dealer Angsuran 1', check_company=True, copy=True,
    )
    clearing_down_payment_account_id = fields.Many2one(
        'account.account', string='Akun Down Payment', check_company=True, copy=True,
    )
    clearing_move_ids = fields.One2many(
        'account.move', 'leasing_clearing_loan_id', string='Clearing AP Leasing',
        readonly=True, copy=False,
    )
    clearing_move_count = fields.Integer(compute='_compute_clearing_move_count', groups='account.group_account_invoice')
    has_active_clearing_move = fields.Boolean(compute='_compute_clearing_move_count', groups='account.group_account_invoice')

    @api.depends('clearing_move_ids.state')
    def _compute_clearing_move_count(self):
        for loan in self:
            loan.clearing_move_count = len(loan.clearing_move_ids)
            loan.has_active_clearing_move = bool(loan.clearing_move_ids.filtered(lambda move: move.state != 'cancel'))

    def _lock_for_leasing_clearing(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(_('Hanya user Accounting/Invoicing yang dapat membuat Clearing AP Leasing.'))
        self.check_access('write')
        if self.company_id not in self.env.companies:
            raise AccessError(_('Aktifkan company leasing sebelum membuat Clearing AP Leasing.'))
        # Match the PO -> loan lock order used by Payment Voucher Leasing.
        if self.purchase_order_id:
            self.purchase_order_id.check_access('read')
            self.purchase_order_id.flush_recordset()
            self.env.cr.execute(SQL('SELECT id FROM purchase_order WHERE id = %s FOR SHARE',
                                    self.purchase_order_id.id))
            self.purchase_order_id.invalidate_recordset()
        self._lock_for_early_settlement()
        self.clearing_move_ids.invalidate_recordset()

    def _flat_has_transactions(self):
        return super()._flat_has_transactions() or bool(self.clearing_move_ids)

    def _check_clearing_before_schedule_reset(self):
        # Historical Effective schedules do not all use _flat_has_transactions.
        # A clearing must protect its original schedule under those policies too.
        if self.filtered('clearing_move_ids'):
            raise UserError(_('Jadwal yang sudah memiliki jurnal Clearing tidak boleh di-reset/dihitung ulang.'))

    def action_compute_amortization_schedule(self):
        self._check_clearing_before_schedule_reset()
        return super().action_compute_amortization_schedule()

    def action_reset(self):
        self._check_clearing_before_schedule_reset()
        return super().action_reset()

    def _check_clearing_before_loan_cancellation(self):
        for loan in self.sorted('id'):
            if loan.clearing_move_ids:
                loan._lock_for_leasing_clearing()
                if loan.clearing_move_ids.filtered(lambda move: move.state != 'cancel'):
                    raise UserError(_(
                        'Review dan batalkan jurnal Clearing aktif terlebih dahulu sebelum '
                        'membatalkan/mengembalikan Leasing Schedule ke Draft.'))

    def action_cancel(self):
        self._check_clearing_before_loan_cancellation()
        return super().action_cancel()

    def action_set_to_draft(self):
        self._check_clearing_before_loan_cancellation()
        return super().action_set_to_draft()

    def write(self, values):
        if _SETTINGS.intersection(values):
            for loan in self.sorted('id'):
                loan._lock_for_leasing_clearing()
                changed = any(loan[name].id != (values[name] or False)
                              for name in _SETTINGS.intersection(values))
                if changed and (loan.state not in ('draft', 'running') or loan.has_active_clearing_move):
                    raise UserError(_(
                        'Pengaturan Clearing hanya dapat diubah pada Draft/Running tanpa jurnal Clearing aktif. '
                        'Batalkan jurnal Draft terlebih dahulu bila perlu memperbaiki pengaturan.'))
        return super().write(values)

    def _prepare_leasing_clearing_move(self):
        self.ensure_one()
        if self.advarr != 'in_advance_addm' or self.state not in ('draft', 'running'):
            raise UserError(_('Clearing AP Leasing hanya untuk ADDM pada status Draft atau Running.'))
        if not self.purchase_order_id:
            raise UserError(_('Purchase Order harus diisi sebelum membuat Clearing AP Leasing.'))
        if self.purchase_order_id.company_id != self.company_id:
            raise UserError(_('Company Purchase Order harus sama dengan company leasing.'))
        partner = self.purchase_order_id.leasing_partner_id
        dealer = self.purchase_order_id.partner_id
        if not partner or not dealer:
            raise UserError(_('Leasing Partner dan Vendor/Dealer harus diisi pada Purchase Order.'))
        for contact in partner | dealer:
            if contact.company_id and contact.company_id != self.company_id:
                raise UserError(_('Partner Clearing harus berasal dari company leasing yang sama.'))
        lines = self.line_ids.sorted(lambda line: (line.date, line.id))
        if not lines or not lines[0].date:
            raise UserError(_('Compute/Import jadwal angsuran terlebih dahulu.'))
        if self.schedule_source == 'import':
            self._validate_imported_schedule()
        elif self.use_rate_conversion:
            self._validate_converted_schedule()
        elif self.compute_method == 'flat':
            self._validate_flat_schedule()
        elif self.compute_method == 'effective_2':
            self._validate_effective2_schedule()

        first = lines[0]
        currency = self.currency_id
        if self.purchase_order_id.currency_id != currency:
            raise UserError(_('Mata uang Purchase Order harus sama dengan mata uang leasing untuk Clearing ini.'))
        installment = ((self.leasing_installment or self.conversion_installment_preview)
                       if self.use_rate_conversion else first.payment)
        otr, balance, installment, dp = (
            self.harga_otr, first.outstanding_balance, installment, self.down_payment_leasing)
        if any(not isfinite(value) or value < 0 for value in (otr, balance, installment, dp)):
            raise UserError(_('Nilai OTR, saldo pokok, cicilan dan Down Payment harus valid dan tidak negatif.'))
        otr, balance, installment, dp = (currency.round(value) for value in (otr, balance, installment, dp))
        if otr <= 0 or installment <= 0:
            raise UserError(_('Harga OTR dan cicilan angsuran pertama harus lebih besar dari nol.'))
        if (not currency.is_zero(otr - balance - installment - dp)
                or not currency.is_zero(self.total_hutang - (otr - dp))
                or not currency.is_zero(first.payment - installment)
                or not currency.is_zero(first.interest)):
            raise UserError(_(
                'Clearing tidak seimbang: OTR harus sama dengan Saldo Pokok angsuran 1 + Cicilan + DP. '
                'Periksa OTR setelah diskon, DP dan Compute/Import jadwal; bunga angsuran pertama ADDM harus 0.'))

        journal = self.clearing_journal_id
        accounts = (self.clearing_account_id, self.long_term_account_id,
                    self.clearing_first_installment_account_id, self.clearing_down_payment_account_id)
        if not journal or any(not account for account in accounts):
            raise UserError(_(
                'Lengkapi Jurnal Clearing, Akun Clearing, Hutang Pokok (Long Term), '
                'Akun AP Dealer Angsuran 1 dan Akun Down Payment pada Loan Settings.'))
        self._check_company(list(_SETTINGS) + ['long_term_account_id'])
        # The legacy Long Term field is not check_company=True; validate that
        # account here as well without changing other leasing flows globally.
        if any(not account.filtered_domain(account._check_company_domain(self.company_id)) for account in accounts):
            raise UserError(_('Seluruh akun Clearing harus sesuai dengan company leasing.'))
        if journal.type != 'general' or not journal.active or journal.company_id != self.company_id:
            raise UserError(_('Pilih jurnal Miscellaneous/Clearing AP Leasing yang aktif pada company leasing.'))
        if journal.currency_id and journal.currency_id != currency:
            raise UserError(_('Mata uang jurnal Clearing harus sama dengan mata uang leasing.'))
        if any(not account.active or account.account_type == 'off_balance' for account in accounts):
            raise UserError(_('Akun Clearing harus aktif dan bukan akun Off-Balance Sheet.'))
        if any(account.account_type in ('asset_receivable', 'liability_payable') for account in accounts[:2]):
            raise UserError(_('Akun Clearing dan Hutang Pokok harus akun buku besar, bukan Receivable/Payable.'))
        if self.analytic_account_id.company_id and self.analytic_account_id.company_id != self.company_id:
            raise UserError(_('Company analytic kendaraan harus sama dengan company leasing.'))
        analytic = {str(self.analytic_account_id.id): 100} if self.analytic_account_id else {}
        values = []
        for label, account, recipient, debit, credit in [
            ('CLEARING AP LEASING', accounts[0], partner, otr, 0),
            ('AP LEASING', accounts[1], partner, 0, balance),
            ('AP DEALER ANGSURAN 1', accounts[2], dealer, 0, installment),
            ('DOWN PAYMENT', accounts[3], dealer, 0, dp),
        ]:
            item = {'name': label, 'account_id': account.id, 'partner_id': recipient.id,
                    'debit': debit, 'credit': credit, 'currency_id': currency.id,
                    'amount_currency': debit - credit, 'analytic_distribution': analytic,
                    'tax_ids': [Command.clear()]}
            if account.account_type in ('asset_receivable', 'liability_payable'):
                item['date_maturity'] = first.date
            values.append(Command.create(item))
        return {
            'move_type': 'entry', 'company_id': self.company_id.id,
            'currency_id': currency.id, 'journal_id': journal.id, 'date': first.date,
            'ref': '%s - %s' % (self.purchase_order_id.name, self.name),
            'partner_id': partner.id, 'auto_post': 'no',
            'leasing_clearing_loan_id': self.id, 'line_ids': values,
        }

    def _clearing_move_action(self, move):
        move.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': _('Clearing AP Leasing'),
                'res_model': 'account.move', 'res_id': move.id, 'view_mode': 'form',
                'views': [(self.env.ref('account.view_move_form').id, 'form')],
                'target': 'current', 'context': {'default_move_type': 'entry'}}

    def action_create_leasing_clearing(self):
        self.ensure_one()
        with self.env.cr.savepoint():
            self._lock_for_leasing_clearing()
            if self.advarr != 'in_advance_addm' or self.state not in ('draft', 'running'):
                raise UserError(_('Clearing AP Leasing hanya untuk ADDM pada status Draft atau Running.'))
            active = self.clearing_move_ids.filtered(lambda move: move.state != 'cancel')
            if active:
                return self._clearing_move_action(active.sorted('id')[-1])
            values = self._prepare_leasing_clearing_move()
            duplicate = self.env['account.move'].search([
                ('company_id', '=', self.company_id.id), ('journal_id', '=', values['journal_id']),
                ('ref', '=', values['ref']), ('state', '!=', 'cancel'),
            ], limit=1)
            if duplicate:
                raise UserError(_('Sudah ada jurnal dengan referensi Clearing yang sama. Review jurnal tersebut sebelum membuat ulang.'))
            move = self.env['account.move'].with_company(self.company_id).with_context(
                _leasing_clearing_token=_CREATE_TOKEN).create(values)
            self.message_post(body=_('Draft Clearing AP Leasing dibuat. Review dan Post melalui Journal Entry.'))
            return self._clearing_move_action(move)

    def action_view_leasing_clearing(self):
        self.ensure_one()
        self.check_access('read')
        moves = self.clearing_move_ids
        moves.check_access('read')
        if len(moves) == 1:
            return self._clearing_move_action(moves)
        return {'type': 'ir.actions.act_window', 'name': _('Clearing AP Leasing'),
                'res_model': 'account.move', 'view_mode': 'list,form',
                'domain': [('id', 'in', moves.ids)],
                'context': {'default_move_type': 'entry', 'create': False}}


class AccountMove(models.Model):
    _inherit = 'account.move'

    leasing_clearing_loan_id = fields.Many2one(
        'account.loan', string='Leasing Schedule (Clearing)', readonly=True,
        copy=False, check_company=True, index=True, ondelete='restrict',
    )

    @api.model_create_multi
    def create(self, values_list):
        if self.env.context.get('_leasing_clearing_token') is not _CREATE_TOKEN and any(
            values.get('leasing_clearing_loan_id', self.env.context.get('default_leasing_clearing_loan_id'))
            for values in values_list
        ):
            raise UserError(_('Gunakan tombol Clearing AP Leasing untuk membuat link jurnal.'))
        return super().create(values_list)

    def write(self, values):
        if 'leasing_clearing_loan_id' in values and any(
            move.leasing_clearing_loan_id.id != (values['leasing_clearing_loan_id'] or False) for move in self
        ):
            raise UserError(_('Link jurnal Clearing ke Leasing Schedule tidak dapat diubah.'))
        return super().write(values)

    def _post(self, soft=True):
        with self.env.cr.savepoint():
            for move in self.filtered('leasing_clearing_loan_id').sorted('id'):
                loan = move.leasing_clearing_loan_id
                loan._lock_for_leasing_clearing()
                if loan.clearing_move_ids.filtered(lambda other: other != move and other.state != 'cancel'):
                    raise UserError(_('Leasing ini sudah memiliki jurnal Clearing aktif lain.'))
                expected = loan._prepare_leasing_clearing_move()
                if any(move[name].id != expected[name] for name in ('journal_id', 'company_id', 'currency_id', 'partner_id')) or (
                    move.move_type != 'entry' or move.date != expected['date'] or move.ref != expected['ref']
                    or move.auto_post != 'no' or len(move.line_ids) != 4
                ):
                    raise UserError(_('Header jurnal Clearing berbeda dari sumber leasing. Batalkan Draft lalu buat ulang.'))
                actual = move.line_ids.sorted('id')
                for line, command in zip(actual, expected['line_ids']):
                    item = command[2]
                    if (any(line[name].id != item[name] for name in ('account_id', 'partner_id', 'currency_id'))
                            or line.name != item['name'] or line.tax_ids or line.tax_repartition_line_id
                            or any(not move.currency_id.is_zero(line[name] - item[name])
                                   for name in ('debit', 'credit', 'amount_currency'))
                            or (line.analytic_distribution or {}) != item['analytic_distribution']
                            or line.date_maturity != item.get('date_maturity', False)):
                        raise UserError(_('Baris jurnal Clearing berbeda dari sumber leasing. Batalkan Draft lalu buat ulang.'))
            return super()._post(soft=soft)

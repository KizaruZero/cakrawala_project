from odoo import Command, api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL, float_compare


class AccountLoan(models.Model):
    _inherit = 'account.loan'

    early_settlement_bill_ids = fields.One2many(
        'account.move', 'early_settlement_loan_id',
        string='Pelunasan Dipercepat', readonly=True, copy=False,
    )
    early_settlement_bill_count = fields.Integer(
        compute='_compute_early_settlement_bill_count',
    )

    @api.depends('early_settlement_bill_ids')
    def _compute_early_settlement_bill_count(self):
        for loan in self:
            loan.early_settlement_bill_count = len(loan.early_settlement_bill_ids)

    def _lock_for_early_settlement(self):
        """Serialize settlement creation/posting and the regular payment wizard."""
        self.ensure_one()
        self.check_access('write')
        if self.company_id not in self.env.companies:
            raise AccessError(_('Aktifkan company leasing sebelum memproses pelunasan.'))
        self.flush_recordset()
        self.env.cr.execute(SQL(
            'SELECT id FROM account_loan WHERE id = %s FOR UPDATE', self.id,
        ))
        self.invalidate_recordset()
        self.line_ids.invalidate_recordset()

    def _early_settlement_schedule(self):
        """Return (original installment number, line) after the LAST posted payment.

        Older gaps are deliberately not added to the tail. Accrued interest and
        LT/ST reclassification journals are not principal installment payments.
        For ADDM schedules, installment #1 is already paid with DP.
        """
        self.ensure_one()
        schedule = list(enumerate(
            self.line_ids.sorted(lambda line: (line.date, line.id)), start=1,
        ))
        last_posted = max((number for number, line in schedule if (
            line.vendor_bill_id.state == 'posted'
            or (self.advarr == 'in_advance_addm' and number == 1)
            or any(move.state == 'posted' and move.is_loan_payment_move
                   for move in line.generated_move_ids)
        )), default=0)
        return [(number, line) for number, line in schedule if number > last_posted]

    def _validate_early_settlement_schedule(self, schedule):
        self.ensure_one()
        if not schedule:
            raise UserError(_('Tidak ada sisa angsuran setelah pembayaran terakhir yang Posted.'))
        for number, line in schedule:
            if (line.vendor_bill_id and line.vendor_bill_id.state != 'cancel') or any(
                move.state != 'cancel' and move.is_loan_payment_move
                for move in line.generated_move_ids
            ):
                raise UserError(_(
                    'Angsuran ke %s sudah memiliki jurnal pembayaran yang belum dibatalkan. '
                    'Periksa jurnal tersebut sebelum membuat pelunasan.', number,
                ))
            if float_compare(line.principal, 0, precision_rounding=self.currency_id.rounding) < 0:
                raise UserError(_('Pokok angsuran ke %s tidak boleh negatif.', number))
        if self.currency_id.is_zero(sum(line.principal for _, line in schedule)):
            raise UserError(_('Total sisa pokok angsuran harus lebih besar dari nol.'))

    def _early_settlement_bill_action(self, bill):
        bill.check_access('read')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pelunasan Dipercepat'),
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'views': [(self.env.ref('account.view_move_form').id, 'form')],
            'target': 'current',
            'context': {'default_move_type': 'in_invoice'},
        }

    def action_create_early_settlement_bill(self):
        """Create ONE draft principal-only bill; never post/pay/close the loan."""
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(_('Hanya user Accounting/Invoicing yang dapat membuat pelunasan.'))
        self._lock_for_early_settlement()
        if self.state != 'running':
            raise UserError(_('Pelunasan Dipercepat hanya tersedia untuk leasing Running.'))
        existing = self.early_settlement_bill_ids.filtered(lambda bill: bill.state != 'cancel')
        if existing:
            return self._early_settlement_bill_action(existing.sorted('id')[-1])

        schedule = self._early_settlement_schedule()
        self._validate_early_settlement_schedule(schedule)
        loan = self.with_company(self.company_id)
        partner = loan._early_settlement_partner()
        account = loan._early_settlement_account()
        journal = self.env['account.journal'].search([
            ('company_id', '=', loan.company_id.id), ('type', '=', 'purchase'),
            ('currency_id', 'in', [False, loan.currency_id.id]),
        ], order='sequence, id', limit=1)
        if not journal:
            raise UserError(_('Siapkan jurnal Vendor Bills pada company dan mata uang leasing.'))

        agreement = loan.agreement_no or loan.name
        plate = loan.plate_number or '-'
        distribution = {str(loan.analytic_account_id.id): 100} if loan.analytic_account_id else {}
        today = fields.Date.context_today(loan)
        bill = self.env['account.move'].with_company(loan.company_id).create({
            'move_type': 'in_invoice',
            'company_id': loan.company_id.id,
            'journal_id': journal.id,
            'partner_id': partner.id,
            'currency_id': loan.currency_id.id,
            'invoice_date': today,
            'date': today,
            'invoice_payment_term_id': partner.property_supplier_payment_term_id.id,
            'invoice_origin': loan.name,
            'ref': f'Pelunasan Dipercepat - {agreement} - {plate}',
            'early_settlement_loan_id': loan.id,
            'invoice_line_ids': [Command.create({
                'sequence': number,
                'name': f'Angsuran ke {number} - {agreement} - {plate}',
                'account_id': account.id,
                'quantity': 1,
                'price_unit': line.principal,
                'discount': 0,
                'tax_ids': [Command.clear()],
                'analytic_distribution': distribution,
                'early_settlement_schedule_line_id': line.id,
            }) for number, line in schedule],
        })
        return self._early_settlement_bill_action(bill)

    def _early_settlement_partner(self):
        """Settlement is payable to the explicit lessor, not the unit dealer."""
        self.ensure_one()
        partner = self.bank_id
        if not partner or not partner.active:
            raise UserError(_('Isi Leasing Partner yang aktif pada Leasing Schedule sebelum membuat pelunasan.'))
        if partner.company_id and partner.company_id != self.company_id:
            raise UserError(_('Leasing Partner harus tersedia pada company leasing terkait.'))
        return partner

    def _early_settlement_account(self):
        """Use the explicit clearing mapping, never fall back to principal debt."""
        self.ensure_one()
        account = self.clearing_account_id
        if not account or not account.active:
            raise UserError(_('Isi Akun Clearing AP Leasing yang aktif di Loan Settings.'))
        if account.account_type in ('asset_receivable', 'liability_payable', 'off_balance'):
            raise UserError(_(
                'Akun Clearing AP Leasing %s tidak dapat digunakan sebagai baris Vendor Bill. '
                'Gunakan akun clearing non-Payable yang sesuai; akun Payable vendor '
                'dipakai otomatis sebagai akun lawan. Hubungi Accounting untuk konfigurasi akun.',
                account.display_name,
            ))
        if self.company_id not in account.company_ids:
            raise UserError(_('Akun Clearing AP Leasing harus tersedia pada company leasing.'))
        return account

    def action_view_early_settlement_bills(self):
        self.ensure_one()
        self.check_access('read')
        if len(self.early_settlement_bill_ids) == 1:
            return self._early_settlement_bill_action(self.early_settlement_bill_ids)
        return {
            'type': 'ir.actions.act_window', 'name': _('Pelunasan Dipercepat'),
            'res_model': 'account.move', 'view_mode': 'list,form',
            'domain': [('early_settlement_loan_id', '=', self.id)],
            'context': {'default_move_type': 'in_invoice'},
        }


class AccountLoanLine(models.Model):
    _inherit = 'account.loan.line'

    early_settlement_invoice_line_ids = fields.One2many(
        'account.move.line', 'early_settlement_schedule_line_id',
        string='Early Settlement Bill Lines', readonly=True, copy=False,
    )

    def _check_no_early_settlement_bill(self):
        for line in self:
            if any(invoice_line.move_id.state != 'cancel'
                   for invoice_line in line.early_settlement_invoice_line_ids):
                raise UserError(_(
                    'Angsuran ke %s sudah tercakup dalam Vendor Bill Pelunasan Dipercepat. '
                    'Periksa atau batalkan bill tersebut sebelum membuat pembayaran angsuran biasa.',
                    line.installment_number,
                ))


class AccountMove(models.Model):
    _inherit = 'account.move'

    early_settlement_loan_id = fields.Many2one(
        'account.loan', string='Leasing Pelunasan Dipercepat',
        readonly=True, copy=False, index=True, check_company=True, ondelete='restrict',
    )
    early_settlement_warning = fields.Text(
        string='Peringatan Nilai Pelunasan', compute='_compute_early_settlement_warning',
        groups='account.group_account_invoice',
    )

    @api.depends('state', 'early_settlement_loan_id', 'currency_id',
                 'invoice_line_ids.price_subtotal', 'invoice_line_ids.display_type',
                 'invoice_line_ids.early_settlement_schedule_line_id',
                 'early_settlement_loan_id.line_ids.principal',
                 'early_settlement_loan_id.line_ids.date',
                 'early_settlement_loan_id.line_ids.vendor_bill_id.state',
                 'early_settlement_loan_id.line_ids.generated_move_ids.state',
                 'early_settlement_loan_id.line_ids.generated_move_ids.is_loan_payment_move',
                 'early_settlement_loan_id.advarr')
    def _compute_early_settlement_warning(self):
        for bill in self:
            bill.early_settlement_warning = False
            if not bill.early_settlement_loan_id or bill.state != 'draft':
                continue
            schedule = bill.early_settlement_loan_id._early_settlement_schedule()
            sources = self.env['account.loan.line'].browse([line.id for _, line in schedule])
            lines = bill.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
            differs = (len(lines) != len(sources)
                       or set(lines.early_settlement_schedule_line_id.ids) != set(sources.ids)
                       or any(not line.early_settlement_schedule_line_id
                              or not bill.currency_id.is_zero(
                                  line.price_subtotal - line.early_settlement_schedule_line_id.principal)
                              for line in lines))
            if differs:
                bill.early_settlement_warning = _(
                    'Nilai/jumlah baris pelunasan berbeda dari jadwal leasing. '
                    'Sisa pokok jadwal: %(expected)s (%(expected_lines)s baris); '
                    'nilai bill sebelum pajak: %(actual)s (%(actual_lines)s baris). '
                    'Ini hanya peringatan; posting tetap diperbolehkan sesuai nilai yang diinput. '
                    'Periksa kesepakatan pelunasan sebelum melanjutkan.',
                    expected=bill.currency_id.format(sum(sources.mapped('principal'))),
                    expected_lines=len(sources), actual=bill.currency_id.format(sum(lines.mapped('price_subtotal'))),
                    actual_lines=len(lines),
                )

    def _validate_early_settlement_bill(self):
        """Retain identity/account/double-payment guards, not amount equality."""
        for bill in self.filtered('early_settlement_loan_id'):
            loan = bill.early_settlement_loan_id
            loan._lock_for_early_settlement()
            if loan.early_settlement_bill_ids.filtered(
                lambda other: other != bill and other.state != 'cancel'
            ):
                raise UserError(_('Leasing ini sudah memiliki Vendor Bill Pelunasan Dipercepat lain yang aktif.'))
            schedule = loan._early_settlement_schedule()
            loan._validate_early_settlement_schedule(schedule)
            account = loan._early_settlement_account()
            partner = loan._early_settlement_partner()
            sources = self.env['account.loan.line'].browse([line.id for _, line in schedule])
            invoice_lines = bill.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
            if (bill.move_type != 'in_invoice' or bill.company_id != loan.company_id
                    or bill.currency_id != loan.currency_id):
                raise UserError(_(
                    'Jenis dokumen, company, atau mata uang bill pelunasan tidak sesuai dengan leasing. '
                    'Batalkan bill draft tersebut dan buat ulang melalui Pelunasan Dipercepat.',
                ))
            if bill.partner_id != partner:
                raise UserError(_(
                    'Vendor pada bill pelunasan harus sama dengan Leasing Partner pada Leasing Schedule (%s). '
                    'Batalkan bill draft tersebut dan buat ulang melalui Pelunasan Dipercepat.',
                    partner.display_name,
                ))
            linked_lines = invoice_lines.filtered('early_settlement_schedule_line_id')
            linked_sources = linked_lines.early_settlement_schedule_line_id
            if (linked_sources - sources or len(linked_lines) != len(linked_sources)):
                raise UserError(_(
                    'Baris pelunasan mengacu ke angsuran di luar sisa angsuran leasing, '
                    'sudah dibayar, atau tercantum ganda. Periksa sumber angsuran sebelum posting.',
                ))
            for line in invoice_lines:
                if line.account_id != account or line.tax_ids:
                    raise UserError(_(
                        'Baris pelunasan harus memakai Akun Clearing AP Leasing dan tanpa pajak. '
                        'Batalkan bill draft yang tidak sesuai dan buat ulang melalui Pelunasan Dipercepat.',
                    ))

    def _post(self, soft=True):
        self._validate_early_settlement_bill()
        warnings = {bill.id: bill.early_settlement_warning for bill in self
                    if bill.early_settlement_loan_id and bill.early_settlement_warning}
        posted = super()._post(soft=soft)
        for bill in posted:
            if bill.id in warnings and bill.state == 'posted':
                bill.message_post(body=warnings[bill.id])
        return posted


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    early_settlement_schedule_line_id = fields.Many2one(
        'account.loan.line', string='Angsuran Pelunasan Dipercepat',
        readonly=True, copy=False, index=True, check_company=True, ondelete='restrict',
    )

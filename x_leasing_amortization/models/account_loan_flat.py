import hashlib
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..lib.flat_schedule import FlatScheduleError, build_flat_schedule


_FLAT_SCHEDULE_VERSION = 'constant_v2'
_FLAT_PARAMETERS = {
    'compute_method', 'company_id', 'purchase_order_id', 'purchase_line_id',
    'harga_otr', 'down_payment_leasing', 'total_hutang', 'amount_borrowed',
    'monthly_installment', 'installment_amount', 'interest_rate_annual', 'interest',
    'duration', 'advarr', 'start_date_leasing', 'date',
    'flat_payment_timing', 'flat_interest_rounding',
}


class AccountLoan(models.Model):
    _inherit = 'account.loan'

    # A distinct table/view, not a second set of accounting installments.
    flat_line_ids = fields.One2many(related='line_ids', string='Amortization Schedule - Bunga Flat', readonly=False)
    flat_payment_timing = fields.Selection([
        ('anniversary', 'Tanggal Mulai Sewa Setiap Bulan'),
        ('end_of_month', 'Akhir Bulan'),
    ], default='anniversary', string='Tanggal Angsuran Flat', copy=True)
    flat_interest_rounding = fields.Selection([
        ('whole_rupiah', 'Rupiah Penuh (IDR)'), ('currency', 'Presisi Mata Uang'),
    ], default='whole_rupiah', string='Pembulatan Bunga Flat', copy=True,
        help='Mata uang selain IDR selalu menggunakan presisi mata uangnya.')
    flat_effective_rate_annual = fields.Float(
        string='Efektif Ekuivalen (% / Tahun)', digits=(16, 10), readonly=True, copy=False,
        help='Rate bulanan ekuivalen dikali 12, seperti kolom Eff. pada contoh kontrak; bukan annual compounded yield.')
    flat_implied_rate_annual = fields.Float(
        string='Flat Aktual (% / Tahun)', digits=(16, 10), readonly=True, copy=False)
    flat_last_auto_installment = fields.Monetary(readonly=True, copy=False, currency_field='currency_id')
    flat_installment_source = fields.Selection(
        [('automatic', 'Otomatis'), ('contract', 'Kontrak')], string='Sumber Cicilan Flat',
        compute='_compute_flat_installment_source')
    schedule_compute_method = fields.Selection(
        [('effective', 'Bunga Efektif'), ('effective_2', 'Bunga Efektif 2'), ('flat', 'Bunga Flat')], readonly=True, copy=False)
    flat_schedule_signature = fields.Char(readonly=True, copy=False)
    # No default: existing equivalent-rate schedules must not be silently
    # relabelled or rewritten when this column is added during upgrade.
    flat_schedule_version = fields.Char(readonly=True, copy=False)
    flat_schedule_needs_compute = fields.Boolean(compute='_compute_flat_schedule_needs_compute')

    @api.depends('monthly_installment', 'installment_amount', 'flat_last_auto_installment')
    def _compute_flat_installment_source(self):
        for loan in self:
            automatic = (loan.flat_last_auto_installment and loan.currency_id.is_zero(
                loan.monthly_installment - loan.flat_last_auto_installment)) or not (
                    loan.monthly_installment or loan.installment_amount)
            loan.flat_installment_source = 'automatic' if automatic else 'contract'

    def _flat_has_transactions(self):
        self.ensure_one()
        lines = self.line_ids
        return bool(lines.vendor_bill_id or lines.monthly_adjustment_move_id or lines.generated_move_ids
                    or lines.early_settlement_invoice_line_ids or self.early_settlement_bill_ids)

    def _flat_fingerprint(self):
        self.ensure_one()
        values = {name: (self[name].id if self._fields[name].type == 'many2one' else self[name])
                  for name in sorted(_FLAT_PARAMETERS)}
        values['auto_installment'] = self.flat_last_auto_installment
        values['rounding'] = self.currency_id.rounding
        values['currency'] = self.currency_id.name
        if self.flat_schedule_version:
            values['allocation_version'] = self.flat_schedule_version
        if self.schedule_date_policy:
            values['date_policy'] = self.schedule_date_policy
            values['due_date'] = str(self.due_date)
            values['manual_dates'] = [(line.id, line.date_is_manual) for line in self.line_ids.sorted('id')]
        values['lines'] = [(str(line.date), line.principal, line.interest)
                           for line in self.line_ids.sorted(lambda line: (line.date, line.id))]
        return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()

    @api.depends(*sorted(_FLAT_PARAMETERS), 'flat_last_auto_installment', 'flat_schedule_signature',
                 'flat_schedule_version', 'state',
                 'due_date', 'schedule_date_policy', 'line_ids.date_is_manual',
                 'line_ids.date', 'line_ids.principal', 'line_ids.interest', 'currency_id.rounding')
    def _compute_flat_schedule_needs_compute(self):
        for loan in self:
            loan.flat_schedule_needs_compute = (
                not loan.flat_schedule_signature or loan.flat_schedule_signature != loan._flat_fingerprint()
                or (loan.state == 'draft' and loan.flat_schedule_version != _FLAT_SCHEDULE_VERSION)
                or (loan.state == 'draft' and loan.schedule_date_policy != 'due_date_anniversary_v1')
            ) if loan.compute_method == 'flat' else loan.schedule_compute_method == 'flat'

    def _flat_settings(self, advarr=None):
        self.ensure_one()
        self._check_schedule_due_date()
        advarr = advarr or self.advarr
        if not advarr:
            raise UserError(_('Pilih Advarr (ADDM atau In Arrears) sebelum Compute Bunga Flat.'))
        if self.harga_otr:
            if self.down_payment_leasing < 0 or self.down_payment_leasing >= self.harga_otr:
                raise UserError(_('Down Payment harus tidak negatif dan lebih kecil dari Harga OTR.'))
            principal = self.harga_otr - self.down_payment_leasing
        else:
            principal = self.total_hutang
        payment = self.monthly_installment
        if self.flat_last_auto_installment and self.currency_id.is_zero(payment - self.flat_last_auto_installment):
            payment = 0
        payment = payment or self.installment_amount
        return {
            'principal': principal, 'annual_flat_rate': self.interest_rate_annual,
            'months': self.duration, 'start_date': self.due_date, 'first_due_date': self.due_date,
            'advance': advarr == 'in_advance_addm', 'installment': payment,
            'currency_rounding': self.currency_id.rounding,
            'interest_rounding': (1 if self.currency_id.name == 'IDR' and self.flat_interest_rounding == 'whole_rupiah'
                                  else self.currency_id.rounding),
            'payment_timing': self.flat_payment_timing or 'anniversary',
        }

    def _flat_result(self, **overrides):
        try:
            return build_flat_schedule(**{**self._flat_settings(), **overrides})
        except FlatScheduleError as error:
            raise UserError(str(error)) from error

    def write(self, values):
        # An explicit user entry, even equal to the previous auto result, locks
        # the contractual installment. Internal compute writes its marker too.
        if ('monthly_installment' in values and 'flat_last_auto_installment' not in values
                and self.filtered(lambda loan: loan.compute_method == 'flat' and loan.state == 'draft')):
            values = {**values, 'flat_last_auto_installment': 0}
        for loan in self:
            relevant = loan.compute_method == 'flat' or values.get('compute_method') == 'flat' or loan.schedule_compute_method == 'flat'
            if not relevant:
                continue
            changed = []
            for name in _FLAT_PARAMETERS.intersection(values):
                current = loan[name].id if loan._fields[name].type == 'many2one' else loan[name]
                proposed = loan._fields[name].convert_to_cache(values[name], loan)
                if current != proposed:
                    changed.append(name)
            if changed and loan.state != 'draft':
                raise UserError(_('Parameter/jadwal Bunga Flat hanya boleh diubah pada status Draft.'))
            if changed and loan.line_ids and loan._flat_has_transactions():
                raise UserError(_('Jadwal sudah terhubung transaksi. Jangan mengubah metode/perhitungan; buat dokumen baru atau lakukan review Accounting.'))
            if values.get('state') == 'running' and loan.state == 'draft' and loan.compute_method == 'flat':
                loan._validate_flat_schedule()
        return super().write(values)

    def action_compute_amortization_schedule(self):
        flats = self.filtered(lambda loan: loan.compute_method == 'flat')
        effective = self - flats
        if not flats:
            result = super().action_compute_amortization_schedule()
            self.write({'schedule_compute_method': 'effective', 'flat_schedule_signature': False,
                        'flat_last_auto_installment': 0, 'flat_schedule_version': False})
            return result
        with self.env.cr.savepoint():
            prepared = []
            for loan in flats.sorted('id'):
                loan._lock_for_early_settlement()
                if loan.state != 'draft':
                    raise UserError(_('Perhitungan ulang hanya dapat dilakukan pada status Draft.'))
                if loan._flat_has_transactions():
                    raise UserError(_('Jadwal sudah terhubung transaksi dan tidak boleh dihapus/dihitung ulang.'))
                prepared.append((loan, loan._flat_result()))
            if effective:
                super(AccountLoan, effective).action_compute_amortization_schedule()
                effective.write({'schedule_compute_method': 'effective', 'flat_schedule_signature': False,
                                 'flat_last_auto_installment': 0, 'flat_schedule_version': False})
            for loan, data in prepared:
                loan.line_ids.unlink()
                self.env['account.loan.line'].create([{
                    'loan_id': loan.id, 'date': row['date'],
                    'principal': float(row['principal']), 'interest': float(row['interest']),
                } for row in data['rows']])
                loan.write({
                    'amount_borrowed': float(data['principal']), 'total_hutang': float(data['principal']),
                    'monthly_installment': float(data['installment']), 'interest': float(data['total_interest']),
                    'flat_last_auto_installment': float(data['installment']) if data['automatic'] else 0,
                    'flat_effective_rate_annual': 0,
                    'flat_implied_rate_annual': float(data['implied_flat_annual_percent']),
                    'schedule_compute_method': 'flat', 'flat_schedule_version': _FLAT_SCHEDULE_VERSION,
                    'schedule_date_policy': 'due_date_anniversary_v1', 'schedule_due_date': loan.due_date,
                })
                loan.flat_schedule_signature = loan._flat_fingerprint()
        return True

    def _validate_flat_schedule(self):
        for loan in self.filtered(lambda item: item.compute_method == 'flat'):
            if loan.flat_schedule_needs_compute:
                raise UserError(_('Klik Compute Flat Schedule dahulu: parameter atau baris angsuran telah berubah.'))
            if loan.flat_schedule_version != _FLAT_SCHEDULE_VERSION:
                # A historical Running schedule retains its original rows and
                # fingerprint checks; do not compare it to the new formula.
                continue
            if loan.state != 'draft' and not loan.schedule_date_policy:
                continue  # Historical Running schedule: preserve its old calendar.
            result = loan._flat_result()
            lines = loan.line_ids.sorted(lambda line: (line.date, line.id))
            if len(lines) != len(result['rows']):
                raise UserError(_('Jumlah angsuran Flat tidak sesuai tenor. Klik Compute Flat Schedule.'))
            for line, row in zip(lines, result['rows']):
                if ((not line.date_is_manual and line.date != row['date'])
                        or not loan.currency_id.is_zero(line.principal - float(row['principal']))
                        or not loan.currency_id.is_zero(line.interest - float(row['interest']))):
                    raise UserError(_('Jadwal Flat tidak sesuai perhitungan kontrak. Klik Compute Flat Schedule.'))

    def action_confirm(self):
        drafts = self.filtered(lambda loan: loan.state == 'draft')
        drafts.filtered(lambda loan: loan.compute_method == 'flat')._validate_flat_schedule()
        if drafts.filtered(lambda loan: loan.compute_method != 'flat' and loan.schedule_compute_method == 'flat'):
            raise UserError(_('Metode berubah ke Bunga Efektif. Compute ulang sebelum Confirm.'))
        return super().action_confirm()

    def action_reset(self):
        for loan in self.filtered(lambda item: item.compute_method == 'flat' or item.schedule_compute_method == 'flat'):
            if loan.state != 'draft' or loan._flat_has_transactions():
                raise UserError(_('Jadwal Flat yang sudah berjalan/terhubung transaksi tidak boleh di-reset.'))
        return super().action_reset()

    def _early_settlement_schedule(self):
        if self.compute_method == 'flat' and self.flat_schedule_signature:
            self._validate_flat_schedule()
        return super()._early_settlement_schedule()

    @api.depends('compute_method', 'total_hutang', 'amount_borrowed', 'monthly_installment')
    def _compute_saldo_pokok_hutang(self):
        effective = self.filtered(lambda loan: loan.compute_method != 'flat')
        super(AccountLoan, effective)._compute_saldo_pokok_hutang()
        for loan in self - effective:
            loan.saldo_pokok_hutang = loan.amount_borrowed or loan.total_hutang

    @api.depends('compute_method', 'monthly_installment', 'duration', 'line_ids.payment')
    def _compute_total_installment_payment(self):
        effective = self.filtered(lambda loan: loan.compute_method != 'flat')
        super(AccountLoan, effective)._compute_total_installment_payment()
        for loan in self - effective:
            loan.total_installment_payment = (sum(loan.line_ids.mapped('payment')) if loan.line_ids
                                              else loan.monthly_installment * loan.duration)

    @api.depends('compute_method', 'total_installment_payment', 'saldo_pokok_hutang', 'line_ids.interest')
    def _compute_total_bunga(self):
        effective = self.filtered(lambda loan: loan.compute_method != 'flat')
        super(AccountLoan, effective)._compute_total_bunga()
        for loan in self - effective:
            loan.total_bunga = (sum(loan.line_ids.mapped('interest')) if loan.line_ids
                                else max(0, loan.total_installment_payment - loan.saldo_pokok_hutang))


class AccountLoanLine(models.Model):
    _inherit = 'account.loan.line'

    flat_display_principal = fields.Monetary(
        string='Pokok', compute='_compute_flat_display_principal', currency_field='currency_id',
        help='Angsuran pertama Flat ditampilkan 0. Pembayarannya tetap mengurangi hutang pokok dalam jurnal.')

    @api.depends('principal', 'installment_number', 'loan_id.compute_method', 'loan_id.flat_schedule_version')
    def _compute_flat_display_principal(self):
        for line in self:
            first_flat = (line.loan_id.compute_method == 'flat'
                          and line.loan_id.flat_schedule_version == _FLAT_SCHEDULE_VERSION
                          and line.installment_number == 1)
            line.flat_display_principal = 0 if first_flat else line.principal

    @api.depends('loan_id.compute_method', 'loan_id.line_ids.date', 'loan_id.line_ids.interest', 'date')
    def _compute_interest_balance(self):
        effective = self.filtered(lambda line: line.loan_id.compute_method != 'flat')
        super(AccountLoanLine, effective)._compute_interest_balance()
        for loan in (self - effective).loan_id:
            remaining = 0
            for line in reversed(loan.line_ids.sorted(lambda item: (item.date, item.id))):
                if line in self:
                    line.interest_balance = remaining
                remaining += line.interest

    def write(self, values):
        if {'principal', 'interest', 'date', 'loan_id'}.intersection(values):
            for line in self.filtered(lambda item: item.loan_id.compute_method == 'flat'):
                if line.loan_id.state != 'draft' or line.loan_id._flat_has_transactions():
                    raise UserError(_('Angsuran Flat yang berjalan/terhubung transaksi tidak boleh diubah.'))
        return super().write(values)

    def unlink(self):
        for loan in self.loan_id.filtered(lambda item: item.compute_method == 'flat'):
            if loan.state != 'draft' or loan._flat_has_transactions():
                raise UserError(_('Angsuran Flat yang berjalan/terhubung transaksi tidak boleh dihapus.'))
        return super().unlink()

    def _generate_monthly_adjustment_entry(self):
        if self.loan_id.compute_method == 'flat' and self.loan_id.flat_schedule_signature:
            self.loan_id._validate_flat_schedule()
        return super()._generate_monthly_adjustment_entry()


class AccountLoanComputeWizard(models.TransientModel):
    _inherit = 'account.loan.compute.wizard'

    flat_duration_months = fields.Integer(string='Tenor Flat (Bulan)')
    flat_monthly_installment = fields.Monetary(string='Cicilan Kontrak Flat', currency_field='currency_id')
    flat_advarr = fields.Selection([
        ('in_advance_addm', 'In Advanced/ADDM'), ('in_arrears', 'In Arrears'),
    ], string='Advarr Flat')
    flat_payment_timing = fields.Selection([
        ('anniversary', 'Tanggal Mulai Sewa Setiap Bulan'), ('end_of_month', 'Akhir Bulan'),
    ], string='Tanggal Angsuran Flat', default='anniversary')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        loan_id = values.get('loan_id') or self.env.context.get('default_loan_id') or self.env.context.get('active_id')
        loan = self.env['account.loan'].browse(loan_id).exists() if loan_id else self.env['account.loan']
        if loan and values.get('compute_method', loan.compute_method) == 'flat':
            values.update({
                'interest_rate': loan.interest_rate_annual,
                'flat_duration_months': loan.duration,
                'flat_monthly_installment': 0 if loan.flat_last_auto_installment else loan.monthly_installment or loan.installment_amount,
                'flat_advarr': loan.advarr, 'flat_payment_timing': loan.flat_payment_timing,
                'loan_amount': loan.harga_otr - loan.down_payment_leasing if loan.harga_otr else loan.total_hutang,
            })
        return values

    def _flat_wizard_result(self):
        self.ensure_one()
        loan = self.loan_id
        settings = loan._flat_settings(advarr=self.flat_advarr)
        if self.start_date != loan.due_date:
            raise UserError(_('Tanggal angsuran mengikuti Tanggal Jatuh Tempo di header leasing.'))
        if not loan.currency_id.is_zero(self.loan_amount - settings['principal']):
            raise UserError(_('Pokok Flat mengikuti Harga OTR dikurangi DP. Ubah nilai tersebut di header leasing.'))
        settings.update({
            'annual_flat_rate': self.interest_rate,
            'months': self.flat_duration_months or loan.duration,
            'installment': self.flat_monthly_installment or loan.installment_amount,
            'start_date': self.start_date,
            'payment_timing': self.flat_payment_timing or 'anniversary',
        })
        try:
            return build_flat_schedule(**settings)
        except FlatScheduleError as error:
            raise UserError(str(error)) from error

    @api.depends('loan_amount', 'interest_rate', 'loan_term', 'start_date',
                 'first_payment_date', 'payment_end_of_month', 'compute_method',
                 'flat_duration_months', 'flat_monthly_installment', 'flat_advarr', 'flat_payment_timing')
    def _compute_preview(self):
        effective = self.filtered(lambda wizard: wizard.compute_method != 'flat')
        super(AccountLoanComputeWizard, effective)._compute_preview()
        for wizard in self - effective:
            if not wizard.loan_id:
                wizard.preview = ''
                continue
            try:
                result = wizard._flat_wizard_result()
            except UserError as error:
                wizard.preview = str(error)
                continue
            rows = result['rows']
            output = ['Flat - Pokok dan Bunga Konstan',
                      'Angsuran | Due Date | Pokok | Bunga | Total | Saldo Pokok | Saldo Bunga']
            visible = rows if len(rows) <= 10 else rows[:5] + [None] + rows[-5:]
            for row in visible:
                if row is None:
                    output.append('...')
                else:
                    amounts = ' | '.join(wizard.currency_id.format(float(row[key])) for key in (
                        'display_principal', 'interest', 'payment', 'outstanding_balance', 'interest_balance'))
                    output.append(f"{row['number']} | {row['date']:%d/%m/%Y} | {amounts}")
            wizard.preview = '\n'.join(output)

    @api.onchange('compute_method')
    def _onchange_compute_method(self):
        # Cancelling a Flat preview must not write the parent through the old
        # sudo onchange. Effective-only previews retain their previous flow.
        effective = self.filtered(lambda wizard: wizard.compute_method != 'flat' and wizard.loan_id.compute_method != 'flat')
        return super(AccountLoanComputeWizard, effective)._onchange_compute_method() if effective else None

    def action_save(self):
        flats = self.filtered(lambda wizard: wizard.compute_method == 'flat')
        if not flats:
            return super().action_save()
        with self.env.cr.savepoint():
            for wizard in flats:
                wizard._flat_wizard_result()
            for wizard in flats:
                loan = wizard.loan_id
                loan.write({
                    'compute_method': 'flat', 'interest_rate_annual': wizard.interest_rate,
                    'duration': wizard.flat_duration_months or loan.duration,
                    'monthly_installment': wizard.flat_monthly_installment,
                    'flat_last_auto_installment': 0,
                    'advarr': wizard.flat_advarr or loan.advarr,
                    'flat_payment_timing': wizard.flat_payment_timing,
                })
                loan.action_compute_amortization_schedule()
            effective = self - flats
            if effective:
                super(AccountLoanComputeWizard, effective).action_save()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

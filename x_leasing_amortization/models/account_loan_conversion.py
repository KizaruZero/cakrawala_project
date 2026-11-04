import hashlib
import json
from math import isfinite

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..lib.interest_conversion import InterestConversionError, build_converted_schedule, quote_interest


_TOKEN = object()
_VERSION = 'annuity_conversion_v1'
_PARAMETERS = {
    'use_rate_conversion', 'interest_input_type', 'quoted_interest_rate', 'compute_method',
    'company_id', 'purchase_order_id', 'purchase_line_id', 'total_hutang', 'amount_borrowed',
    'harga_otr', 'down_payment_leasing', 'monthly_installment', 'installment_amount',
    'duration', 'advarr', 'due_date', 'start_date_leasing', 'date', 'interest', 'interest_rate_annual', 'flat_interest_rounding',
}
_METADATA = {'conversion_signature', 'conversion_version', 'conversion_auto_installment'}


class AccountLoan(models.Model):
    _inherit = 'account.loan'

    # Deliberately no database default: upgrading must not opt historical rows in.
    use_rate_conversion = fields.Boolean(readonly=True, copy=True)
    interest_input_type = fields.Selection([('flat', 'Flat'), ('effective', 'Efektif')],
                                         string='Jenis Input Bunga', tracking=True)
    quoted_interest_rate = fields.Float(string='Bunga Input (% / Tahun)', digits=(16, 10), tracking=True)
    converted_flat_rate = fields.Float(string='Bunga Flat (% / Tahun)', digits=(16, 10), compute='_compute_conversion_quote')
    converted_effective_rate = fields.Float(string='Bunga Efektif (% / Tahun)', digits=(16, 10), compute='_compute_conversion_quote')
    conversion_installment_preview = fields.Monetary(string='Cicilan Hasil Konversi', compute='_compute_conversion_quote')
    conversion_message = fields.Char(compute='_compute_conversion_quote')
    conversion_signature = fields.Char(readonly=True, copy=False)
    conversion_version = fields.Char(readonly=True, copy=False)
    conversion_auto_installment = fields.Monetary(readonly=True, copy=False)
    conversion_needs_compute = fields.Boolean(compute='_compute_conversion_needs_compute')

    @api.model
    def default_get(self, names):
        values = super().default_get(names)
        if 'use_rate_conversion' in names and values.get('schedule_source', 'compute') != 'import':
            values.setdefault('use_rate_conversion', True)
            if 'interest_input_type' in names:
                values.setdefault('interest_input_type', 'flat')
        return values

    @api.model_create_multi
    def create(self, values_list):
        prepared = []
        for values in values_list:
            values = dict(values)
            imported = values.get('schedule_source') == 'import'
            values.setdefault('use_rate_conversion', not imported)
            if imported and values['use_rate_conversion']:
                raise UserError(_('Jadwal Import Kontrak tidak menggunakan konversi/Compute.'))
            if values['use_rate_conversion']:
                if values.get('state', 'draft') != 'draft':
                    raise UserError(_('Jadwal konversi baru harus dibuat sebagai Draft, lalu Compute dan Confirm.'))
                values.setdefault('interest_input_type', 'flat')
                values['compute_method'] = 'effective'  # Canonical rows; no user-facing calculation-method selector.
            if self.env.context.get('_conversion_token') is not _TOKEN and any(values.get(key) for key in _METADATA):
                raise UserError(_('Metadata konversi hanya dibuat oleh Compute.'))
            prepared.append(values)
        return super().create(prepared)

    def _conversion_settings(self):
        self.ensure_one()
        if not self.advarr:
            raise UserError(_('Pilih Advarr (ADDM atau In Arrears) sebelum konversi bunga.'))
        if any(not isfinite(value) or value < 0 for value in (self.harga_otr, self.down_payment_leasing)):
            raise UserError(_('Harga OTR dan Down Payment harus angka valid yang tidak negatif.'))
        payment = self.monthly_installment
        if self.conversion_auto_installment and self.currency_id.is_zero(payment - self.conversion_auto_installment):
            payment = 0
        principal = self.total_hutang or (self.harga_otr - self.down_payment_leasing)
        return {
            'principal': principal, 'months': self.duration, 'input_type': self.interest_input_type,
            'annual_rate': self.quoted_interest_rate, 'advance': self.advarr == 'in_advance_addm',
            'installment': payment or self.installment_amount,
            'currency_rounding': self.currency_id.rounding,
        }

    def _conversion_result(self):
        self.ensure_one()
        try:
            return build_converted_schedule(
                **self._conversion_settings(), first_due_date=self.due_date,
                interest_rounding=(1 if self.currency_id.name == 'IDR' and self.flat_interest_rounding == 'whole_rupiah'
                                   else self.currency_id.rounding))
        except InterestConversionError as error:
            raise UserError(str(error)) from error

    @api.depends('use_rate_conversion', 'interest_input_type', 'quoted_interest_rate', 'duration', 'advarr',
                 'total_hutang', 'harga_otr', 'down_payment_leasing', 'monthly_installment',
                 'installment_amount', 'conversion_auto_installment', 'currency_id.rounding')
    def _compute_conversion_quote(self):
        for loan in self:
            loan.converted_flat_rate = loan.converted_effective_rate = loan.conversion_installment_preview = 0
            loan.conversion_message = False
            if not loan.use_rate_conversion:
                continue
            try:
                data = quote_interest(**loan._conversion_settings())
            except (InterestConversionError, UserError) as error:
                loan.conversion_message = str(error)
                continue
            loan.converted_flat_rate = float(data['flat_rate'])
            loan.converted_effective_rate = float(data['effective_rate'])
            loan.conversion_installment_preview = float(data['installment'])
            if data['contract_mismatch']:
                loan.conversion_message = _(
                    'Cicilan kontrak diutamakan. Bunga aktual sesuai cicilan: Flat %(flat).10f%% / Efektif %(effective).10f%% per tahun; berbeda dari tarif input.',
                    flat=float(data['flat_rate']), effective=float(data['effective_rate']))

    def _conversion_fingerprint(self):
        self.ensure_one()
        values = {name: self[name].id if self._fields[name].type == 'many2one' else self[name]
                  for name in sorted(_PARAMETERS)}
        values.update({'auto': self.conversion_auto_installment, 'version': self.conversion_version,
                       'currency': self.currency_id.name, 'rounding': self.currency_id.rounding,
                       'rows': [(str(line.date), line.principal, line.interest, line.date_is_manual)
                                for line in self.line_ids.sorted(lambda line: (line.date, line.id))]})
        return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()

    @api.depends(*sorted(_PARAMETERS), 'conversion_signature', 'conversion_version', 'conversion_auto_installment',
                 'line_ids.date', 'line_ids.principal', 'line_ids.interest', 'line_ids.date_is_manual', 'currency_id.rounding')
    def _compute_conversion_needs_compute(self):
        for loan in self:
            loan.conversion_needs_compute = bool(loan.use_rate_conversion and (
                loan.conversion_version != _VERSION or not loan.conversion_signature
                or loan.conversion_signature != loan._conversion_fingerprint()))

    def _validate_converted_schedule(self):
        for loan in self.filtered('use_rate_conversion'):
            if loan.schedule_source == 'import' or loan.compute_method != 'effective' or loan.conversion_needs_compute:
                raise UserError(_('Klik Compute Jadwal dahulu: parameter atau angsuran konversi telah berubah.'))
            data = loan._conversion_result()
            lines = loan.line_ids.sorted(lambda line: (line.date, line.id))
            if (len(lines) != len(data['rows']) or not loan.currency_id.is_zero(loan.interest - float(data['total_interest']))
                    or not loan.currency_id.is_zero(loan.amount_borrowed - float(data['principal']))):
                raise UserError(_('Total/tenor jadwal konversi tidak sesuai. Compute ulang sebelum transaksi.'))
            for line, row in zip(lines, data['rows']):
                if ((not line.date_is_manual and line.date != row['date'])
                        or not loan.currency_id.is_zero(line.principal - float(row['principal']))
                        or not loan.currency_id.is_zero(line.interest - float(row['interest']))):
                    raise UserError(_('Angsuran tidak sesuai rumus konversi. Compute ulang sebelum transaksi.'))

    def _seal_converted_schedule(self):
        for loan in self:
            loan.with_context(_conversion_token=_TOKEN).write({'conversion_signature': loan._conversion_fingerprint()})

    def write(self, values):
        values = dict(values)
        if self.env.context.get('_conversion_token') is not _TOKEN and _METADATA.intersection(values):
            raise UserError(_('Metadata konversi tidak dapat diubah langsung.'))
        # Selecting the new input basis is an explicit opt-in for an old Draft.
        if values.get('interest_input_type'):
            if self.filtered(lambda loan: loan.schedule_source == 'import'):
                raise UserError(_('Jadwal Import Kontrak tidak dihitung ulang melalui konversi.'))
            values.update(use_rate_conversion=True, compute_method='effective')
        for loan in self.filtered(lambda item: item.use_rate_conversion or values.get('use_rate_conversion')):
            changed = any((loan[name].id if loan._fields[name].type == 'many2one' else loan[name])
                          != loan._fields[name].convert_to_cache(values[name], loan)
                          for name in _PARAMETERS.intersection(values))
            if changed and (loan.state != 'draft' or loan._flat_has_transactions()):
                raise UserError(_('Parameter konversi hanya boleh diubah pada Draft yang belum terhubung transaksi.'))
            if loan.use_rate_conversion and (values.get('use_rate_conversion') is False
                                             or values.get('compute_method', 'effective') != 'effective'):
                raise UserError(_('Gunakan Jenis Input Bunga, bukan mengganti metode jadwal konversi.'))
            if values.get('state') == 'running' and loan.state == 'draft':
                loan._validate_converted_schedule()
        if ('monthly_installment' in values and self.env.context.get('_conversion_token') is not _TOKEN
                and self.filtered('use_rate_conversion')):
            values['conversion_auto_installment'] = 0
        return super().write(values)

    @api.onchange('total_hutang', 'interest_rate_annual', 'start_date_leasing')
    def _onchange_leasing_sync_standard(self):
        other = self.filtered(lambda loan: not loan.use_rate_conversion)
        if other:
            super(AccountLoan, other)._onchange_leasing_sync_standard()
        for loan in self - other:
            loan.amount_borrowed = loan.total_hutang
            if loan.start_date_leasing:
                loan.date = loan.start_date_leasing

    def action_compute_amortization_schedule(self):
        converted = self.filtered('use_rate_conversion')
        if not converted:
            return super().action_compute_amortization_schedule()
        with self.env.cr.savepoint():
            prepared = []
            for loan in converted.sorted('id'):
                loan._lock_for_early_settlement()
                if loan.state != 'draft' or loan._flat_has_transactions() or loan.schedule_source == 'import':
                    raise UserError(_('Compute konversi hanya untuk Draft tanpa transaksi, bukan Import Kontrak.'))
                prepared.append((loan, loan._conversion_result()))
            other = self - converted
            if other:
                super(AccountLoan, other).action_compute_amortization_schedule()
            for loan, data in prepared:
                loan.line_ids.unlink()
                self.env['account.loan.line'].create([{
                    'loan_id': loan.id, 'date': row['date'],
                    'principal': float(row['principal']), 'interest': float(row['interest']),
                } for row in data['rows']])
                internal = loan.with_context(_conversion_token=_TOKEN)
                internal.write({
                    'amount_borrowed': float(data['principal']), 'total_hutang': float(data['principal']),
                    'monthly_installment': float(data['installment']), 'interest': float(data['total_interest']),
                    'interest_rate_annual': float(data['effective_rate']),
                    'conversion_auto_installment': float(data['installment']) if data['automatic'] else 0,
                    'conversion_version': _VERSION, 'schedule_compute_method': 'effective',
                    'schedule_date_policy': 'due_date_anniversary_v1', 'schedule_due_date': loan.due_date,
                })
                internal.write({'conversion_signature': loan._conversion_fingerprint()})
        return True

    def action_open_rate_conversion_wizard(self):
        self.ensure_one()
        if self.state != 'draft' or self._flat_has_transactions() or self.schedule_source == 'import':
            raise UserError(_('Preview konversi hanya untuk Draft tanpa transaksi.'))
        return {'type': 'ir.actions.act_window', 'name': _('Compute Jadwal Leasing'),
                'res_model': 'account.loan.compute.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_loan_id': self.id, 'default_conversion_preview': True}}

    def action_confirm(self):
        for loan in self.filtered(lambda loan: loan.state == 'draft' and loan.use_rate_conversion).sorted('id'):
            loan._lock_for_early_settlement()
            loan._validate_converted_schedule()
        return super().action_confirm()

    def action_reset(self):
        if self.filtered(lambda loan: loan.use_rate_conversion and (loan.state != 'draft' or loan._flat_has_transactions())):
            raise UserError(_('Jadwal konversi yang berjalan/terhubung transaksi tidak boleh di-reset.'))
        return super().action_reset()

    def _early_settlement_schedule(self):
        self._validate_converted_schedule()
        return super()._early_settlement_schedule()

    @api.depends('use_rate_conversion', 'total_hutang', 'amount_borrowed', 'monthly_installment')
    def _compute_saldo_pokok_hutang(self):
        other = self.filtered(lambda loan: not loan.use_rate_conversion)
        super(AccountLoan, other)._compute_saldo_pokok_hutang()
        for loan in self - other:
            loan.saldo_pokok_hutang = loan.amount_borrowed or loan.total_hutang

    @api.depends('use_rate_conversion', 'monthly_installment', 'duration', 'line_ids.payment')
    def _compute_total_installment_payment(self):
        other = self.filtered(lambda loan: not loan.use_rate_conversion)
        super(AccountLoan, other)._compute_total_installment_payment()
        for loan in self - other:
            loan.total_installment_payment = sum(loan.line_ids.mapped('payment')) if loan.line_ids else loan.monthly_installment * loan.duration

    @api.depends('use_rate_conversion', 'state', 'total_installment_payment', 'total_hutang', 'line_ids.interest',
                 'interest_input_type', 'quoted_interest_rate', 'duration', 'advarr', 'harga_otr',
                 'down_payment_leasing', 'monthly_installment', 'installment_amount',
                 'conversion_auto_installment', 'currency_id.rounding')
    def _compute_total_bunga(self):
        other = self.filtered(lambda loan: not loan.use_rate_conversion)
        super(AccountLoan, other)._compute_total_bunga()
        for loan in self - other:
            if loan.state == 'draft':
                # Quote the current inputs, even before Compute or while old
                # Draft rows await an explicit recompute. Do not rewrite the
                # canonical interest budget, signature or any installment here.
                try:
                    data = quote_interest(**loan._conversion_settings())
                    loan.total_bunga = float(data['total_interest'])
                except (InterestConversionError, UserError):
                    loan.total_bunga = 0  # Input error is shown by conversion_message.
            else:
                loan.total_bunga = sum(loan.line_ids.mapped('interest')) if loan.line_ids else max(0, loan.total_installment_payment - loan.total_hutang)


class AccountLoanLine(models.Model):
    _inherit = 'account.loan.line'

    @api.depends('loan_id.use_rate_conversion', 'loan_id.line_ids.interest', 'loan_id.line_ids.date', 'date')
    def _compute_interest_balance(self):
        other = self.filtered(lambda line: not line.loan_id.use_rate_conversion)
        super(AccountLoanLine, other)._compute_interest_balance()
        for loan in (self - other).loan_id:
            remaining = 0
            for line in reversed(loan.line_ids.sorted(lambda item: (item.date, item.id))):
                if line in self:
                    line.interest_balance = remaining
                remaining += line.interest

    @api.model_create_multi
    def create(self, values_list):
        for values in values_list:
            loan = self.env['account.loan'].browse(values.get('loan_id'))
            if loan.use_rate_conversion and (loan.state != 'draft' or loan._flat_has_transactions()):
                raise UserError(_('Tidak boleh menambah angsuran konversi yang berjalan/terhubung transaksi.'))
        return super().create(values_list)

    def write(self, values):
        if {'principal', 'interest', 'date', 'loan_id'}.intersection(values):
            loans = self.loan_id
            if values.get('loan_id'):
                loans |= self.env['account.loan'].browse(values['loan_id'])
            if loans.filtered(lambda loan: loan.use_rate_conversion and (loan.state != 'draft' or loan._flat_has_transactions())):
                raise UserError(_('Angsuran konversi yang berjalan/terhubung transaksi tidak boleh diubah.'))
        return super().write(values)

    def unlink(self):
        if self.loan_id.filtered(lambda loan: loan.use_rate_conversion and (loan.state != 'draft' or loan._flat_has_transactions())):
            raise UserError(_('Angsuran konversi yang berjalan/terhubung transaksi tidak boleh dihapus.'))
        return super().unlink()

    def _generate_monthly_adjustment_entry(self):
        if self.loan_id.use_rate_conversion:
            if self.loan_id.state != 'running':
                raise UserError(_('Accrued bunga jadwal konversi hanya untuk leasing Running.'))
            self.loan_id._validate_converted_schedule()
            if not self.interest:
                return False
        return super()._generate_monthly_adjustment_entry()


class AccountLoanComputeWizard(models.TransientModel):
    _inherit = 'account.loan.compute.wizard'

    conversion_preview = fields.Boolean()
    conversion_input_type = fields.Selection([('flat', 'Flat'), ('effective', 'Efektif')], string='Jenis Input Bunga')
    conversion_input_rate = fields.Float(string='Bunga Input (% / Tahun)', digits=(16, 10))
    conversion_months = fields.Integer(string='Tenor (Bulan)')
    conversion_contract_installment = fields.Monetary(string='Cicilan Kontrak (Opsional)', currency_field='currency_id')
    conversion_advarr = fields.Selection([('in_advance_addm', 'In Advanced/ADDM'), ('in_arrears', 'In Arrear / ADDB')], string='Advarr')
    conversion_flat_rate = fields.Float(string='Bunga Flat (% / Tahun)', digits=(16, 10), compute='_compute_conversion_rates')
    conversion_effective_rate = fields.Float(string='Bunga Efektif (% / Tahun)', digits=(16, 10), compute='_compute_conversion_rates')

    @api.model
    def default_get(self, names):
        values = super().default_get(names)
        loan_id = values.get('loan_id') or self.env.context.get('default_loan_id') or self.env.context.get('active_id')
        loan = self.env['account.loan'].browse(loan_id).exists() if loan_id else self.env['account.loan']
        if loan and (loan.use_rate_conversion or self.env.context.get('default_conversion_preview')):
            payment = loan.monthly_installment
            if loan.conversion_auto_installment and loan.currency_id.is_zero(payment - loan.conversion_auto_installment):
                payment = 0
            values.update({
                'conversion_preview': True, 'loan_amount': loan.total_hutang or loan.harga_otr - loan.down_payment_leasing,
                'start_date': loan.due_date, 'conversion_input_type': loan.interest_input_type or (
                    'flat' if loan.compute_method == 'flat' else 'effective'),
                'conversion_input_rate': loan.quoted_interest_rate if loan.use_rate_conversion else loan.interest_rate_annual,
                'conversion_months': loan.duration, 'conversion_contract_installment': payment or loan.installment_amount,
                'conversion_advarr': loan.advarr,
            })
        return values

    def _conversion_wizard_result(self):
        self.ensure_one()
        loan = self.loan_id
        if (not loan or loan.state != 'draft' or loan._flat_has_transactions() or loan.schedule_source == 'import'):
            raise UserError(_('Preview konversi hanya untuk Draft tanpa transaksi, bukan Import Kontrak.'))
        if (not loan.currency_id.is_zero(self.loan_amount - (loan.total_hutang or loan.harga_otr - loan.down_payment_leasing))
                or self.start_date != loan.due_date):
            raise UserError(_('Pokok dan First Due Date mengikuti header leasing.'))
        if not self.conversion_advarr:
            raise UserError(_('Pilih Advarr terlebih dahulu.'))
        try:
            return build_converted_schedule(
                principal=self.loan_amount, months=self.conversion_months,
                input_type=self.conversion_input_type, annual_rate=self.conversion_input_rate,
                advance=self.conversion_advarr == 'in_advance_addm', installment=self.conversion_contract_installment,
                currency_rounding=loan.currency_id.rounding, first_due_date=self.start_date,
                interest_rounding=1 if loan.currency_id.name == 'IDR' and loan.flat_interest_rounding == 'whole_rupiah' else loan.currency_id.rounding)
        except InterestConversionError as error:
            raise UserError(str(error)) from error

    @api.depends('conversion_preview', 'loan_amount', 'start_date', 'conversion_input_type', 'conversion_input_rate',
                 'conversion_months', 'conversion_contract_installment', 'conversion_advarr')
    def _compute_conversion_rates(self):
        for wizard in self:
            wizard.conversion_flat_rate = wizard.conversion_effective_rate = 0
            if wizard.conversion_preview:
                try:
                    result = wizard._conversion_wizard_result()
                    wizard.conversion_flat_rate = float(result['flat_rate'])
                    wizard.conversion_effective_rate = float(result['effective_rate'])
                except UserError:
                    pass  # The exact input error is displayed in Preview below.

    @api.depends('loan_amount', 'interest_rate', 'loan_term', 'start_date', 'first_payment_date',
                 'payment_end_of_month', 'compute_method', 'flat_duration_months', 'flat_monthly_installment',
                 'flat_advarr', 'flat_payment_timing', 'effective2_duration_months', 'conversion_preview',
                 'conversion_input_type', 'conversion_input_rate', 'conversion_months',
                 'conversion_contract_installment', 'conversion_advarr')
    def _compute_preview(self):
        other = self.filtered(lambda wizard: not wizard.conversion_preview)
        super(AccountLoanComputeWizard, other)._compute_preview()
        for wizard in self - other:
            try:
                data = wizard._conversion_wizard_result()
            except UserError as error:
                wizard.preview = str(error)
                continue
            output = [f"Flat {data['flat_rate']:.10f}% / Efektif {data['effective_rate']:.10f}% per tahun",
                      'Alokasi Efektif - ADDM: Bunga Angsuran Pertama 0' if wizard.conversion_advarr == 'in_advance_addm' else 'Alokasi Efektif - In Arrears',
                      'Angsuran | Due Date | Pokok | Bunga | Total | Saldo Pokok | Saldo Bunga']
            if data['contract_mismatch']:
                output.insert(0, 'Cicilan kontrak diutamakan; bunga aktual berbeda dari tarif input.')
            rows = data['rows']
            for row in rows if len(rows) <= 10 else rows[:5] + [None] + rows[-5:]:
                if row is None:
                    output.append('...')
                else:
                    amounts = ' | '.join(wizard.currency_id.format(float(row[key])) for key in (
                        'principal', 'interest', 'payment', 'outstanding_balance', 'interest_balance'))
                    output.append(f"{row['number']} | {row['date']:%d/%m/%Y} | {amounts}")
            wizard.preview = '\n'.join(output)

    @api.onchange('compute_method')
    def _onchange_compute_method(self):
        other = self.filtered(lambda wizard: not wizard.conversion_preview)
        return super(AccountLoanComputeWizard, other)._onchange_compute_method() if other else None

    def action_save(self):
        converted = self.filtered('conversion_preview')
        if not converted:
            return super().action_save()
        with self.env.cr.savepoint():
            for wizard in converted:
                wizard._conversion_wizard_result()
            for wizard in converted:
                wizard.loan_id.write({
                    'interest_input_type': wizard.conversion_input_type, 'quoted_interest_rate': wizard.conversion_input_rate,
                    'duration': wizard.conversion_months, 'monthly_installment': wizard.conversion_contract_installment,
                    'advarr': wizard.conversion_advarr,
                })
                wizard.loan_id.action_compute_amortization_schedule()
            other = self - converted
            if other:
                super(AccountLoanComputeWizard, other).action_save()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

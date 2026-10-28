import hashlib
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..lib.effective2_schedule import Effective2ScheduleError, build_effective2_schedule


_PARAMETERS = {
    'compute_method', 'company_id', 'total_hutang', 'amount_borrowed', 'interest',
    'monthly_installment', 'installment_amount', 'interest_rate_annual', 'duration', 'due_date',
}


class AccountLoan(models.Model):
    _inherit = 'account.loan'

    effective2_schedule_signature = fields.Char(readonly=True, copy=False)

    def _effective2_settings(self):
        self.ensure_one()
        self._check_schedule_due_date()
        return {
            'principal': self.total_hutang, 'annual_rate': self.interest_rate_annual,
            'months': self.duration, 'first_due_date': self.due_date,
            'installment': self.monthly_installment or self.installment_amount,
            'currency_rounding': self.currency_id.rounding,
        }

    def _effective2_result(self, **overrides):
        try:
            return build_effective2_schedule(**{**self._effective2_settings(), **overrides})
        except Effective2ScheduleError as error:
            raise UserError(str(error)) from error

    def _effective2_fingerprint(self):
        self.ensure_one()
        values = {name: self[name].id if self._fields[name].type == 'many2one' else self[name]
                  for name in sorted(_PARAMETERS)}
        values.update({
            'currency': self.currency_id.name, 'rounding': self.currency_id.rounding,
            'date_policy': self.schedule_date_policy,
            'lines': [(str(line.date), line.principal, line.interest, line.date_is_manual)
                      for line in self.line_ids.sorted(lambda line: (line.date, line.id))],
        })
        return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()

    def write(self, values):
        for loan in self.filtered(lambda item: (
                item.compute_method == 'effective_2' or item.schedule_compute_method == 'effective_2'
                or values.get('compute_method') == 'effective_2')):
            changed = any((loan[name].id if loan._fields[name].type == 'many2one' else loan[name])
                          != loan._fields[name].convert_to_cache(values[name], loan)
                          for name in _PARAMETERS.intersection(values))
            if changed and (loan.state != 'draft' or loan._flat_has_transactions()):
                raise UserError(_('Parameter Bunga Efektif 2 hanya dapat diubah pada Draft yang belum terhubung transaksi.'))
            if values.get('state') == 'running' and loan.state == 'draft' and loan.compute_method == 'effective_2':
                loan._validate_effective2_schedule()
        return super().write(values)

    def action_compute_amortization_schedule(self):
        new_method = self.filtered(lambda loan: loan.compute_method == 'effective_2')
        if not new_method:
            return super().action_compute_amortization_schedule()
        with self.env.cr.savepoint():
            prepared = []
            for loan in new_method.sorted('id'):
                loan._lock_for_early_settlement()
                if loan.state != 'draft' or loan._flat_has_transactions():
                    raise UserError(_('Compute Bunga Efektif 2 hanya tersedia pada Draft yang belum terhubung transaksi.'))
                prepared.append((loan, loan._effective2_result()))
            legacy = self - new_method
            if legacy:
                super(AccountLoan, legacy).action_compute_amortization_schedule()
            for loan, data in prepared:
                loan.line_ids.unlink()
                self.env['account.loan.line'].create([{
                    'loan_id': loan.id, 'date': row['date'],
                    'principal': float(row['principal']), 'interest': float(row['interest']),
                } for row in data['rows']])
                loan.write({
                    'amount_borrowed': float(data['principal']), 'monthly_installment': float(data['installment']),
                    'interest': float(data['total_interest']), 'schedule_compute_method': 'effective_2',
                    'schedule_date_policy': 'due_date_anniversary_v1', 'schedule_due_date': loan.due_date,
                    'flat_schedule_signature': False, 'flat_schedule_version': False, 'flat_last_auto_installment': 0,
                })
                loan.effective2_schedule_signature = loan._effective2_fingerprint()
        return True

    def _validate_effective2_schedule(self):
        for loan in self:
            if (not loan.effective2_schedule_signature
                    or loan.effective2_schedule_signature != loan._effective2_fingerprint()):
                raise UserError(_('Klik Compute dahulu: parameter atau jadwal Bunga Efektif 2 telah berubah.'))
            result = loan._effective2_result()
            lines = loan.line_ids.sorted(lambda line: (line.date, line.id))
            if len(lines) != len(result['rows']):
                raise UserError(_('Jumlah angsuran Bunga Efektif 2 tidak sesuai tenor. Klik Compute ulang.'))
            for line, row in zip(lines, result['rows']):
                if ((not line.date_is_manual and line.date != row['date'])
                        or not loan.currency_id.is_zero(line.principal - float(row['principal']))
                        or not loan.currency_id.is_zero(line.interest - float(row['interest']))):
                    raise UserError(_('Jadwal tidak sesuai perhitungan Bunga Efektif 2. Klik Compute ulang.'))

    def action_confirm(self):
        drafts = self.filtered(lambda loan: loan.state == 'draft')
        drafts.filtered(lambda loan: loan.compute_method == 'effective_2')._validate_effective2_schedule()
        if drafts.filtered(lambda loan: loan.compute_method != 'effective_2' and loan.schedule_compute_method == 'effective_2'):
            raise UserError(_('Compute ulang setelah mengganti metode Bunga Efektif 2.'))
        return super().action_confirm()

    def _early_settlement_schedule(self):
        if self.compute_method == 'effective_2':
            self._validate_effective2_schedule()
        return super()._early_settlement_schedule()

    def action_reset(self):
        for loan in self.filtered(lambda item: item.compute_method == 'effective_2'
                                  or item.schedule_compute_method == 'effective_2'):
            if loan.state != 'draft' or loan._flat_has_transactions():
                raise UserError(_('Jadwal Bunga Efektif 2 yang berjalan/terhubung transaksi tidak boleh di-reset.'))
        return super().action_reset()

    @api.depends('compute_method', 'total_hutang', 'amount_borrowed', 'monthly_installment')
    def _compute_saldo_pokok_hutang(self):
        other = self.filtered(lambda loan: loan.compute_method != 'effective_2')
        super(AccountLoan, other)._compute_saldo_pokok_hutang()
        for loan in self - other:
            loan.saldo_pokok_hutang = loan.total_hutang

    @api.depends('compute_method', 'monthly_installment', 'duration', 'line_ids.payment')
    def _compute_total_installment_payment(self):
        other = self.filtered(lambda loan: loan.compute_method != 'effective_2')
        super(AccountLoan, other)._compute_total_installment_payment()
        for loan in self - other:
            loan.total_installment_payment = (sum(loan.line_ids.mapped('payment')) if loan.line_ids
                                              else loan.monthly_installment * loan.duration)

    @api.depends('compute_method', 'total_installment_payment', 'total_hutang', 'line_ids.interest')
    def _compute_total_bunga(self):
        other = self.filtered(lambda loan: loan.compute_method != 'effective_2')
        super(AccountLoan, other)._compute_total_bunga()
        for loan in self - other:
            loan.total_bunga = (sum(loan.line_ids.mapped('interest')) if loan.line_ids
                                else max(0, loan.total_installment_payment - loan.total_hutang))


class AccountLoanLine(models.Model):
    _inherit = 'account.loan.line'

    @api.model_create_multi
    def create(self, values_list):
        for values in values_list:
            loan = self.env['account.loan'].browse(values.get('loan_id'))
            if loan and loan.compute_method == 'effective_2' and (loan.state != 'draft' or loan._flat_has_transactions()):
                raise UserError(_('Tidak dapat menambah angsuran Bunga Efektif 2 yang berjalan/terhubung transaksi.'))
        return super().create(values_list)

    def write(self, values):
        if {'principal', 'interest', 'date', 'loan_id'}.intersection(values):
            for loan in self.loan_id.filtered(lambda item: item.compute_method == 'effective_2'):
                if loan.state != 'draft' or loan._flat_has_transactions():
                    raise UserError(_('Angsuran Bunga Efektif 2 yang berjalan/terhubung transaksi tidak boleh diubah.'))
        return super().write(values)

    def unlink(self):
        for loan in self.loan_id.filtered(lambda item: item.compute_method == 'effective_2'):
            if loan.state != 'draft' or loan._flat_has_transactions():
                raise UserError(_('Angsuran Bunga Efektif 2 yang berjalan/terhubung transaksi tidak boleh dihapus.'))
        return super().unlink()

    def _generate_monthly_adjustment_entry(self):
        if self.loan_id.compute_method == 'effective_2':
            self.loan_id._validate_effective2_schedule()
        return super()._generate_monthly_adjustment_entry()


class AccountLoanComputeWizard(models.TransientModel):
    _inherit = 'account.loan.compute.wizard'

    effective2_duration_months = fields.Integer(string='Tenor Efektif 2 (Bulan)')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        loan_id = values.get('loan_id') or self.env.context.get('default_loan_id') or self.env.context.get('active_id')
        loan = self.env['account.loan'].browse(loan_id).exists() if loan_id else self.env['account.loan']
        if loan and values.get('compute_method', loan.compute_method) == 'effective_2':
            values.update({'loan_amount': loan.total_hutang, 'interest_rate': loan.interest_rate_annual,
                           'effective2_duration_months': loan.duration, 'start_date': loan.due_date})
        return values

    def _effective2_wizard_result(self):
        self.ensure_one()
        loan = self.loan_id
        if not loan:
            raise UserError(_('Pilih Leasing Schedule sebelum Compute Bunga Efektif 2.'))
        if (not loan.currency_id.is_zero(self.loan_amount - loan.total_hutang)
                or self.start_date != loan.due_date):
            raise UserError(_('Pokok dan tanggal mengikuti Total Hutang dan Tanggal Jatuh Tempo di header.'))
        return loan._effective2_result(annual_rate=self.interest_rate, months=self.effective2_duration_months)

    @api.depends('loan_amount', 'interest_rate', 'loan_term', 'start_date',
                 'first_payment_date', 'payment_end_of_month', 'compute_method',
                 'flat_duration_months', 'flat_monthly_installment', 'flat_advarr', 'flat_payment_timing',
                 'effective2_duration_months')
    def _compute_preview(self):
        other = self.filtered(lambda wizard: wizard.compute_method != 'effective_2')
        super(AccountLoanComputeWizard, other)._compute_preview()
        for wizard in self - other:
            if not wizard.loan_id:
                wizard.preview = ''
                continue
            try:
                data = wizard._effective2_wizard_result()
            except UserError as error:
                wizard.preview = str(error)
                continue
            output = ['Bunga Efektif 2 - Bunga Sejak Angsuran Pertama',
                      'Angsuran | Due Date | Pokok | Bunga | Total | Saldo Pokok | Saldo Bunga']
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
        for wizard in self.filtered(lambda item: item.compute_method == 'effective_2' and item.loan_id):
            wizard.effective2_duration_months = wizard.loan_id.duration
            wizard.loan_amount = wizard.loan_id.total_hutang
            wizard.interest_rate = wizard.loan_id.interest_rate_annual
            wizard.start_date = wizard.loan_id.due_date
        other = self.filtered(lambda wizard: wizard.compute_method != 'effective_2'
                              and wizard.loan_id.compute_method != 'effective_2')
        return super(AccountLoanComputeWizard, other)._onchange_compute_method() if other else None

    def action_save(self):
        new_method = self.filtered(lambda wizard: wizard.compute_method == 'effective_2')
        if not new_method:
            return super().action_save()
        with self.env.cr.savepoint():
            for wizard in new_method:
                wizard._effective2_wizard_result()
            for wizard in new_method:
                wizard.loan_id.write({'compute_method': 'effective_2', 'interest_rate_annual': wizard.interest_rate,
                                      'duration': wizard.effective2_duration_months})
                wizard.loan_id.action_compute_amortization_schedule()
            other = self - new_method
            if other:
                super(AccountLoanComputeWizard, other).action_save()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

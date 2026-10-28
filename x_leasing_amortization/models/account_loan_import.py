import hashlib
import json
from decimal import Decimal

from odoo import api, fields, models, _
from odoo.exceptions import UserError


_IMPORT_TOKEN = object()
_METADATA = {'schedule_source', 'import_key', 'import_schedule_signature',
             'import_expected_interest', 'import_first_principal_zero'}
_FINANCIAL = {'company_id', 'compute_method', 'total_hutang', 'amount_borrowed', 'interest',
              'monthly_installment', 'interest_rate_annual', 'duration', 'due_date'}


class AccountLoan(models.Model):
    _inherit = 'account.loan'

    schedule_source = fields.Selection([('compute', 'Compute'), ('import', 'Import Kontrak')],
                                       default='compute', required=True, readonly=True, copy=False)
    import_key = fields.Char(string='Import Key', readonly=True, copy=False, index=True)
    import_schedule_signature = fields.Char(readonly=True, copy=False)
    import_expected_interest = fields.Monetary(readonly=True, copy=False)
    import_first_principal_zero = fields.Boolean(readonly=True, copy=False)
    _import_key_unique = models.Constraint('UNIQUE(company_id, import_key)',
                                           'Import Key sudah digunakan pada company ini.')

    @api.model_create_multi
    def create(self, values_list):
        if self.env.context.get('_leasing_import_token') is not _IMPORT_TOKEN:
            if any(values.get('schedule_source') == 'import' or any(values.get(name) for name in _METADATA - {'schedule_source'})
                   for values in values_list):
                raise UserError(_('Gunakan menu Import Leasing Schedules untuk jadwal kontrak.'))
        return super().create(values_list)

    def write(self, values):
        if self.env.context.get('_leasing_import_token') is not _IMPORT_TOKEN:
            if any(name in values and any(loan[name] != values[name] for loan in self) for name in _METADATA):
                raise UserError(_('Sumber dan identitas impor tidak dapat diubah langsung.'))
        for loan in self.filtered(lambda item: item.schedule_source == 'import'):
            if _FINANCIAL.intersection(values) and (loan.state != 'draft' or loan._flat_has_transactions()):
                raise UserError(_('Parameter jadwal impor yang berjalan/terhubung transaksi tidak boleh diubah.'))
            if values.get('state') == 'draft' and loan.state != 'draft':
                raise UserError(_('Jadwal kontrak impor yang sudah diproses tidak boleh dikembalikan ke Draft.'))
            if values.get('state') == 'running' and loan.state == 'draft':
                loan._validate_imported_schedule()
        return super().write(values)

    def copy(self, default=None):
        if self.schedule_source == 'import':
            raise UserError(_('Untuk kontrak impor baru, upload file dengan Import Key dan Agreement No. baru.'))
        return super().copy(default)

    def _import_fingerprint(self):
        self.ensure_one()
        payload = {name: self[name].id if self._fields[name].type == 'many2one' else self[name]
                   for name in sorted(_FINANCIAL | {'import_key', 'import_expected_interest', 'import_first_principal_zero'})}
        payload['rounding'] = self.currency_id.rounding
        payload['rows'] = [(str(line.date), line.principal, line.interest)
                           for line in self.line_ids.sorted(lambda item: (item.date, item.id))]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    def _seal_imported_schedule(self):
        self.ensure_one()
        self.with_context(_leasing_import_token=_IMPORT_TOKEN).write({
            'import_schedule_signature': self._import_fingerprint(),
        })
        self._validate_imported_schedule()

    def _validate_imported_schedule(self):
        for loan in self.filtered(lambda item: item.schedule_source == 'import'):
            if not loan.import_schedule_signature or loan.import_schedule_signature != loan._import_fingerprint():
                raise UserError(_('Jadwal impor telah berubah dari file kontrak. Upload kontrak baru atau koreksi perubahan sebelum Confirm/transaksi.'))
            lines = loan.line_ids.sorted(lambda item: (item.date, item.id))
            if len(lines) != loan.duration or not lines or lines[0].date != loan.due_date:
                raise UserError(_('Tenor/tanggal pertama jadwal impor tidak sesuai header.'))
            if len(set(lines.mapped('date'))) != len(lines):
                raise UserError(_('Due Date jadwal impor tidak boleh duplikat.'))
            principal = sum((Decimal(str(line.principal)) for line in lines), Decimal(0))
            interest = sum((Decimal(str(line.interest)) for line in lines), Decimal(0))
            if (principal != Decimal(str(loan.total_hutang)) or principal != Decimal(str(loan.amount_borrowed))
                    or interest != Decimal(str(loan.import_expected_interest)) or interest != Decimal(str(loan.interest))
                    or any(line.principal < 0 or line.interest < 0 for line in lines)):
                raise UserError(_('Total pokok/bunga jadwal impor tidak sesuai kontrak; saldo akhir harus nol.'))

    def action_compute_amortization_schedule(self):
        if self.filtered(lambda loan: loan.schedule_source == 'import'):
            raise UserError(_('Jadwal Import Kontrak tidak dihitung ulang oleh Compute. Buat dokumen baru untuk menggunakan rumus Compute.'))
        return super().action_compute_amortization_schedule()

    def _validate_flat_schedule(self):
        imported = self.filtered(lambda loan: loan.schedule_source == 'import')
        imported._validate_imported_schedule()
        return super(AccountLoan, self - imported)._validate_flat_schedule()

    def _validate_effective2_schedule(self):
        imported = self.filtered(lambda loan: loan.schedule_source == 'import')
        imported._validate_imported_schedule()
        return super(AccountLoan, self - imported)._validate_effective2_schedule()

    def action_confirm(self):
        self.filtered(lambda loan: loan.state == 'draft')._validate_imported_schedule()
        return super().action_confirm()

    def action_reset(self):
        if self.filtered(lambda loan: loan.schedule_source == 'import'):
            raise UserError(_('Reset akan menghapus jadwal kontrak. Gunakan dokumen baru; jadwal impor tidak di-reset.'))
        return super().action_reset()

    def _early_settlement_schedule(self):
        self._validate_imported_schedule()
        return super()._early_settlement_schedule()

    @api.depends('schedule_source', 'compute_method', 'total_hutang', 'amount_borrowed', 'monthly_installment')
    def _compute_saldo_pokok_hutang(self):
        imported = self.filtered(lambda loan: loan.schedule_source == 'import')
        super(AccountLoan, self - imported)._compute_saldo_pokok_hutang()
        for loan in imported:
            loan.saldo_pokok_hutang = loan.total_hutang

    @api.depends('schedule_source', 'compute_method', 'monthly_installment', 'duration', 'line_ids.payment')
    def _compute_total_installment_payment(self):
        imported = self.filtered(lambda loan: loan.schedule_source == 'import')
        super(AccountLoan, self - imported)._compute_total_installment_payment()
        for loan in imported:
            loan.total_installment_payment = sum(loan.line_ids.mapped('payment'))

    @api.depends('schedule_source', 'compute_method', 'total_installment_payment', 'total_hutang', 'line_ids.interest')
    def _compute_total_bunga(self):
        imported = self.filtered(lambda loan: loan.schedule_source == 'import')
        super(AccountLoan, self - imported)._compute_total_bunga()
        for loan in imported:
            loan.total_bunga = sum(loan.line_ids.mapped('interest'))

    @api.depends('schedule_source', 'compute_method', 'flat_schedule_signature', 'line_ids.principal', 'line_ids.interest', 'line_ids.date')
    def _compute_flat_schedule_needs_compute(self):
        imported = self.filtered(lambda loan: loan.schedule_source == 'import')
        super(AccountLoan, self - imported)._compute_flat_schedule_needs_compute()
        for loan in imported:
            loan.flat_schedule_needs_compute = False


class AccountLoanLine(models.Model):
    _inherit = 'account.loan.line'

    def write(self, values):
        if {'principal', 'interest', 'date', 'loan_id'}.intersection(values):
            loans = self.loan_id
            if values.get('loan_id'):
                loans |= self.env['account.loan'].browse(values['loan_id'])
            for loan in loans.filtered(lambda item: item.schedule_source == 'import'):
                changed = any(
                    (line[name].id if line._fields[name].type == 'many2one' else line[name])
                    != line._fields[name].convert_to_cache(values[name], line)
                    for line in self for name in {'principal', 'interest', 'loan_id'}.intersection(values))
                if changed:
                    raise UserError(_('Pokok/bunga jadwal impor mengikuti file kontrak dan tidak dapat diedit langsung.'))
                if loan.state != 'draft' or loan._flat_has_transactions():
                    raise UserError(_('Angsuran impor yang berjalan/terhubung transaksi tidak boleh diubah.'))
        return super().write(values)

    @api.model_create_multi
    def create(self, values_list):
        for values in values_list:
            loan = self.env['account.loan'].browse(values.get('loan_id'))
            if loan.schedule_source == 'import' and (loan.state != 'draft' or loan._flat_has_transactions()):
                raise UserError(_('Tidak dapat menambah angsuran pada jadwal impor yang berjalan/terhubung transaksi.'))
        return super().create(values_list)

    def unlink(self):
        for loan in self.loan_id.filtered(lambda item: item.schedule_source == 'import'):
            if loan.state != 'draft' or loan._flat_has_transactions():
                raise UserError(_('Angsuran impor yang berjalan/terhubung transaksi tidak boleh dihapus.'))
        return super().unlink()

    @api.depends('principal', 'installment_number', 'loan_id.compute_method', 'loan_id.flat_schedule_version',
                 'loan_id.schedule_source', 'loan_id.import_first_principal_zero')
    def _compute_flat_display_principal(self):
        super()._compute_flat_display_principal()
        for line in self.filtered(lambda item: item.loan_id.schedule_source == 'import'
                                  and item.loan_id.import_first_principal_zero and item.installment_number == 1):
            line.flat_display_principal = 0

    def _generate_monthly_adjustment_entry(self):
        self.loan_id._validate_imported_schedule()
        return super()._generate_monthly_adjustment_entry()

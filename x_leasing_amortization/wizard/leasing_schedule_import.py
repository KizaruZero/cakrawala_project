import base64
import binascii
from collections import defaultdict

from odoo import Command, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL

from ..lib.schedule_import import ADVARR, METHODS, ScheduleImportError, number, read_workbook, validate_rows
from ..models.account_loan_import import _IMPORT_TOKEN


class LeasingScheduleImport(models.TransientModel):
    _name = 'leasing.schedule.import'
    _description = 'Import Leasing Contract Schedules'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    file = fields.Binary(string='File XLSX', required=True, attachment=False)
    filename = fields.Char()

    def action_download_template(self):
        return {'type': 'ir.actions.act_url', 'target': 'download',
                'url': '/x_leasing_amortization/static/templates/Template_Import_Leasing.xlsx'}

    def _resolve(self, model, domain, label):
        record = self.env[model].with_company(self.company_id).search(domain, limit=2)
        if len(record) != 1:
            raise UserError(_('%s: data tidak ditemukan atau tidak unik. Gunakan nama/kode persis dari company yang dipilih.', label))
        record.check_access('read')
        return record

    def _prepare_contracts(self, workbook):
        company = self.company_id
        lines = defaultdict(list)
        for row in workbook['Angsuran']:
            lines[str(row['Import Key'])].append(row)
        seen, prepared = set(), []
        loan_model = self.env['account.loan'].with_context(active_test=False).with_company(company)
        for header in workbook['Header']:
            key = header['Import Key']
            if not isinstance(key, str) or len(key) > 80 or key in seen:
                raise UserError(_('Header baris %s: Import Key harus teks unik, maksimal 80 karakter.', header['_row']))
            seen.add(key)
            if loan_model.search_count([('company_id', '=', company.id), ('import_key', '=', key)]):
                raise UserError(_('Import Key %s sudah pernah diupload. Jadwal lama tidak ditimpa.', key))
            if header['Compute Method'] not in METHODS or header['Advarr'] not in ADVARR:
                raise UserError(_('Header %s: gunakan Compute Method dan Advarr dari dropdown template.', key))
            data = validate_rows(header, lines.pop(key, []), company.currency_id.rounding)
            vendor = self._resolve('res.partner', [('name', '=', str(header['Vendor'])),
                ('company_id', 'in', [False, company.id])], f'{key}: Vendor')
            # Optional legacy identifiers must not block a draft contract import.
            # Link only an unambiguous, readable vehicle in the selected company;
            # preserve the file's plate without guessing or creating Fleet data.
            plate = str(header['Plate Number']) if header.get('Plate Number') not in (None, '') else ''
            vehicle = self.env['fleet.vehicle'].with_company(company)
            if plate:
                matches = vehicle.search([('license_plate', '=', plate), ('company_id', '=', company.id)], limit=2)
                if len(matches) == 1:
                    matches.check_access('read')
                    vehicle = matches
            agreement = str(header['Agreement No.']) if header.get('Agreement No.') not in (None, '') else ''
            accounts = {}
            for column, field in [('Principal Account', 'long_term_account_id'),
                                  ('Short Term Account', 'short_term_account_id'),
                                  ('Interest Expense Account', 'expense_account_id'),
                                  ('Accrued Interest Account', 'accrued_interest_account_id')]:
                account = self._resolve('account.account', [('code', '=', str(header[column])),
                    ('company_ids', 'in', company.ids)], f'{key}: {column}')
                if account.account_type in ('asset_receivable', 'liability_payable', 'off_balance'):
                    raise UserError(_('%s: gunakan akun hutang/beban, bukan Receivable/Payable/Off Balance.', column))
                if field == 'expense_account_id' and not account.account_type.startswith('expense'):
                    raise UserError(_('Interest Expense Account harus bertipe Expense.'))
                if field != 'expense_account_id' and not account.account_type.startswith('liability'):
                    raise UserError(_('%s harus bertipe Liability.', column))
                accounts[field] = account.id
            journal = self._resolve('account.journal', [('code', '=', str(header['Interest Journal'])),
                ('company_id', '=', company.id), ('type', '=', 'general')], f'{key}: Interest Journal')
            prepared.append({
                'company_id': company.id, 'state': 'draft', 'schedule_source': 'import', 'import_key': key,
                'compute_method': METHODS[header['Compute Method']], 'schedule_compute_method': METHODS[header['Compute Method']],
                'agreement_no': agreement, 'nomor_kontrak_leasing': str(header.get('Leasing Contract No.') or ''),
                'vendor_id': vendor.id, 'vehicle_id': vehicle.id, 'import_plate_number': plate,
                'start_date_leasing': data['start'],
                'date': data['start'], 'due_date': data['due'], 'duration': data['duration'],
                'total_hutang': data['principal'], 'amount_borrowed': data['principal'],
                'monthly_installment': data['installment'], 'interest_rate_annual': data['rate'],
                'import_expected_interest': data['interest'], 'interest': data['interest'],
                'harga_otr': float(number(header.get('Harga OTR') or 0, f'{key} Harga OTR', quantum=company.currency_id.rounding)),
                'down_payment_leasing': float(number(header.get('Down Payment') or 0, f'{key} DP', quantum=company.currency_id.rounding)),
                'advarr': ADVARR[header['Advarr']], 'journal_id': journal.id,
                'import_first_principal_zero': data['zero_first'], 'flat_schedule_version': 'import_v1',
                'line_ids': [Command.create(row) for row in data['rows']], **accounts,
            })
        if lines:
            raise UserError(_('Angsuran memiliki Import Key yang tidak ada di Header: %s', ', '.join(lines)))
        return prepared

    def action_import(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_invoice') or self.company_id not in self.env.companies:
            raise AccessError(_('Import leasing hanya untuk Accounting/Invoicing pada company yang aktif.'))
        if not self.filename or not self.filename.lower().endswith('.xlsx'):
            raise UserError(_('Gunakan file .xlsx sesuai template.'))
        if not self.file or len(self.file) > 7 * 1024 * 1024:
            raise UserError(_('Upload file XLSX, maksimal 5 MB.'))
        try:
            raw = base64.b64decode(self.file, validate=True)
            workbook = read_workbook(raw)
            with self.env.cr.savepoint():
                # Serialize imports in a company, including the duplicate checks.
                self.env.cr.execute(SQL('SELECT pg_advisory_xact_lock(%s, %s)', 19513008, self.company_id.id))
                values = self._prepare_contracts(workbook)
                loans = self.env['account.loan'].with_company(self.company_id).with_context(
                    _leasing_import_token=_IMPORT_TOKEN).create(values)
                for loan in loans:
                    loan._seal_imported_schedule()
        except (ScheduleImportError, binascii.Error) as error:
            raise UserError(str(error)) from error
        return {'type': 'ir.actions.act_window', 'name': _('Imported Leasing Schedules'),
                'res_model': 'account.loan', 'view_mode': 'list,form', 'domain': [('id', 'in', loans.ids)],
                'context': {'create': False}}

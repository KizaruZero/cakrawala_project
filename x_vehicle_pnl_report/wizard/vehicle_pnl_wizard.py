# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class VehiclePnlReportWizard(models.TransientModel):
    _name = 'vehicle.pnl.report.wizard'
    _description = 'Wizard Laporan Laba Rugi Kendaraan'

    date_to = fields.Date(
        string='Per Tanggal',
        required=True,
        default=fields.Date.context_today,
        help='Batas tanggal pelaporan (otomatis hari ini).'
    )
    search_query = fields.Char(
        string='Cari Armada',
        help='Ketik Nomor Polisi atau Nama Akun Analitik untuk memfilter daftar armada.'
    )
    line_ids = fields.One2many(
        'vehicle.pnl.report.wizard.line',
        'wizard_id',
        string='Daftar Kendaraan'
    )

    @api.model
    def _get_active_analytic_account_ids(self):
        """Accounts with accessible Analytic Items, not only unarchived accounts.

        Keep the existing transaction requirement (any date/account type), but
        respect the selected companies and native analytic record rules.
        """
        groups = self.env['account.analytic.line'].with_context(active_test=False)._read_group(
            [('account_id', '!=', False), ('company_id', 'in', self.env.companies.ids + [False])],
            groupby=['account_id'],
        )
        return [account.id for account, in groups]

    @api.model
    def _resolve_analytic_account_for_vehicle(self, vehicle, active_accounts=None):
        """Resolusi akun analitik untuk kendaraan via 3 jalur:
        1. Many2one langsung pada fleet.vehicle
        2. Relasi vehicle_id pada account.analytic.account
        3. Kesamaan Nomor Polisi (license_plate)
        """
        if vehicle.analytic_account_id:
            return vehicle.analytic_account_id

        # 2. Cek di active_accounts jika disediakan
        if active_accounts and vehicle.id:
            acc = active_accounts.filtered(lambda a: a.vehicle_id.id == vehicle.id)
            if acc:
                return acc[0]
            if vehicle.license_plate:
                v_plate = vehicle.license_plate.strip().upper()
                acc = active_accounts.filtered(lambda a: a.license_plate and a.license_plate.strip().upper() == v_plate)
                if acc:
                    return acc[0]

        # 3. Fallback search ke tabel account.analytic.account
        domain = []
        if vehicle.license_plate and vehicle.id:
            domain = ['|', ('license_plate', '=ilike', vehicle.license_plate.strip()), ('vehicle_id', '=', vehicle.id)]
        elif vehicle.license_plate:
            domain = [('license_plate', '=ilike', vehicle.license_plate.strip())]
        elif vehicle.id:
            domain = [('vehicle_id', '=', vehicle.id)]

        if domain:
            acc = self.env['account.analytic.account'].with_context(active_test=False).search(
                domain + [('company_id', 'in', self.env.companies.ids + [False])], limit=1)
            if acc:
                return acc

        return self.env['account.analytic.account'].browse()

    @api.model
    def _get_eligible_vehicles(self):
        """Ambil SEMUA armada pada company aktif.

        Kendaraan tanpa akun analitik atau tanpa Analytic Items tetap ditampilkan
        (laporannya akan bernilai 0). Semua status Fleet, termasuk Inactive,
        tanpa status, dan kendaraan arsip, diperbolehkan. Hak akses dan company
        aktif tetap berlaku.

        Akun analitik yang punya Analytic Items tetap dikembalikan sebagai
        kandidat resolusi akun (3-way matching: Many2one langsung, relasi balik
        vehicle_id, kesamaan Nomor Polisi).
        """
        active_account_ids = self._get_active_analytic_account_ids()
        ActiveAccounts = self.env['account.analytic.account'].with_context(active_test=False).search([
            ('id', 'in', active_account_ids),
            ('company_id', 'in', self.env.companies.ids + [False]),
        ]) if active_account_ids else self.env['account.analytic.account'].browse()

        # No transaction, operational-status or archive filter; do not bypass
        # record rules with sudo.
        Vehicle = self.env['fleet.vehicle'].with_context(active_test=False)
        vehicles = Vehicle.search(
            [('company_id', 'in', self.env.companies.ids + [False])], order='license_plate asc')

        return vehicles, ActiveAccounts

    @api.model
    def default_get(self, fields_list):
        res = super(VehiclePnlReportWizard, self).default_get(fields_list)
        
        vehicles, active_accounts = self._get_eligible_vehicles()

        lines = []
        for v in vehicles:
            acc = self._resolve_analytic_account_for_vehicle(v, active_accounts)
            # Auto-healing: sinkronkan ke fleet.vehicle jika belum terisi
            if acc and not v.analytic_account_id:
                try:
                    v.sudo().write({'analytic_account_id': acc.id})
                except Exception:
                    pass

            lines.append((0, 0, {
                'selected': False,
                'vehicle_id': v.id,
                'analytic_account_id': acc.id if acc else (v.analytic_account_id.id if v.analytic_account_id else False),
            }))

        res['line_ids'] = lines
        res['date_to'] = fields.Date.context_today(self)
        return res

    @api.onchange('search_query')
    def _onchange_search_query(self):
        """Filter daftar kendaraan berdasarkan input pencarian tanpa menghilangkan pilihan yang sudah dicentang."""
        # Simpan ID kendaraan yang sedang terpilih
        selected_vids = {l.vehicle_id.id for l in self.line_ids if l.selected and l.vehicle_id}

        vehicles, active_accounts = self._get_eligible_vehicles()
        query = (self.search_query or '').strip().lower()

        new_lines = []
        for v in vehicles:
            acc = self._resolve_analytic_account_for_vehicle(v, active_accounts)
            nopol = (v.license_plate or '').lower()
            acc_name = ((acc and acc.name) or (v.analytic_account_id and v.analytic_account_id.name) or '').lower()
            acc_code = ((acc and acc.code) or (v.analytic_account_id and v.analytic_account_id.code) or '').lower()
            is_selected = v.id in selected_vids

            # Tampilkan jika cocok dengan pencarian ATAU jika kendaraan tersebut sudah dicentang
            if not query or query in nopol or query in acc_name or query in acc_code or is_selected:
                new_lines.append((0, 0, {
                    'selected': is_selected,
                    'vehicle_id': v.id,
                    'analytic_account_id': acc.id if acc else (v.analytic_account_id.id if v.analytic_account_id else False),
                }))

        self.line_ids = [(5, 0, 0)] + new_lines

    def action_preview_report(self):
        """Buka pratinjau QWeb HTML Laporan Laba Rugi Kendaraan di browser tanpa unduh file."""
        self.ensure_one()
        selected_lines = self.line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_('Silakan pilih minimal satu kendaraan dengan mencentang kotak pilihan.'))

        report_action = self.env.ref('x_vehicle_pnl_report.action_report_vehicle_pnl').report_action(self)
        report_action['report_type'] = 'qweb-html'
        report_action.pop('close_on_report_download', None)
        return report_action

    def action_print_report(self):
        """Trigger pencetakan laporan PDF Laba Rugi Kendaraan untuk kendaraan yang dipilih."""
        self.ensure_one()
        selected_lines = self.line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_('Silakan pilih minimal satu kendaraan dengan mencentang kotak pilihan.'))

        report_action = self.env.ref('x_vehicle_pnl_report.action_report_vehicle_pnl').report_action(self)
        report_action['close_on_report_download'] = True
        return report_action


class VehiclePnlReportWizardLine(models.TransientModel):
    _name = 'vehicle.pnl.report.wizard.line'
    _description = 'Line Kendaraan Wizard PnL'

    wizard_id = fields.Many2one('vehicle.pnl.report.wizard', string='Wizard', ondelete='cascade')
    selected = fields.Boolean(string='Pilih', default=False)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Kendaraan', required=True)
    license_plate = fields.Char(string='Nomor Polisi', related='vehicle_id.license_plate', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', readonly=True)
    state_name = fields.Char(string='Status Fleet', related='vehicle_id.state_id.name', readonly=True)

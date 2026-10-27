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
        """Ambil account_id yang memiliki mutasi transaksi di Analytic Items (account.analytic.line)."""
        self.env.cr.execute("""
            SELECT DISTINCT account_id 
            FROM account_analytic_line 
            WHERE account_id IS NOT NULL
        """)
        return [r[0] for r in self.env.cr.fetchall()]

    @api.model
    def _get_eligible_vehicles(self):
        """Ambil armada yang memenuhi kriteria ganda:
        1. Memiliki akun analitik yang tercatat di Analytic Items (account.analytic.line).
        2. Status armada adalah Leased atau Non-Leased (selain Inactive).
        """
        active_account_ids = self._get_active_analytic_account_ids()
        if not active_account_ids:
            return self.env['fleet.vehicle'].browse()

        return self.env['fleet.vehicle'].search([
            ('analytic_account_id', 'in', active_account_ids),
            ('state_id.name', 'in', ('Leased', 'Non-Leased')),
        ], order='license_plate asc')

    @api.model
    def default_get(self, fields_list):
        res = super(VehiclePnlReportWizard, self).default_get(fields_list)
        
        vehicles = self._get_eligible_vehicles()

        lines = []
        for v in vehicles:
            lines.append((0, 0, {
                'selected': False,
                'vehicle_id': v.id,
            }))

        res['line_ids'] = lines
        res['date_to'] = fields.Date.context_today(self)
        return res

    @api.onchange('search_query')
    def _onchange_search_query(self):
        """Filter daftar kendaraan berdasarkan input pencarian tanpa menghilangkan pilihan yang sudah dicentang."""
        # Simpan ID kendaraan yang sedang terpilih
        selected_vids = {l.vehicle_id.id for l in self.line_ids if l.selected and l.vehicle_id}

        vehicles = self._get_eligible_vehicles()
        query = (self.search_query or '').strip().lower()

        new_lines = []
        for v in vehicles:
            nopol = (v.license_plate or '').lower()
            acc_name = (v.analytic_account_id.name or '').lower()
            acc_code = (v.analytic_account_id.code or '').lower()
            is_selected = v.id in selected_vids

            # Tampilkan jika cocok dengan pencarian ATAU jika kendaraan tersebut sudah dicentang
            if not query or query in nopol or query in acc_name or query in acc_code or is_selected:
                new_lines.append((0, 0, {
                    'selected': is_selected,
                    'vehicle_id': v.id,
                }))

        self.line_ids = [(5, 0, 0)] + new_lines

    def action_print_report(self):
        """Trigger pencetakan laporan PDF PnL Kendaraan untuk kendaraan yang dipilih."""
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
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', related='vehicle_id.analytic_account_id', readonly=True)
    state_name = fields.Char(string='Status Fleet', related='vehicle_id.state_id.name', readonly=True)

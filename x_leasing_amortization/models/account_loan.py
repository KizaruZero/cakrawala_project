# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountLoan(models.Model):
    """Extend account.loan with leasing-specific header fields."""
    _inherit = 'account.loan'

    # ---- Relasi ke Purchase Order ----
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        tracking=True,
        index=True,
    )

    # ---- Account Configurations (Override & New) ----
    long_term_account_id = fields.Many2one(
        'account.account',
        string="Hutang Pokok (Long Term)",
        help="Akun untuk menampung nilai hutang pokok (Principal) atas kendaraan/aset leasing. Nilainya akan berkurang seiring dengan cicilan bulanan."
    )
    
    short_term_account_id = fields.Many2one(
        'account.account',
        string="Hutang Jangka Pendek (Short Term)",
        help="Bagian dari hutang leasing yang akan jatuh tempo dalam waktu kurang dari 1 tahun. Digunakan untuk keperluan reklasifikasi akhir tahun."
    )
    
    expense_account_id = fields.Many2one(
        'account.account',
        string="Beban Bunga (Expense)",
        help="Akun beban/biaya riil (Interest Expense) untuk mencatat pengeluaran biaya bunga setiap bulannya."
    )

    accrued_interest_account_id = fields.Many2one(
        'account.account',
        string="Hutang Bunga Sementara (Accrued)",
        company_dependent=True,
        domain="[('account_type', 'in', ('liability_current', 'liability_payable'))]",
        help="Akun hutang sementara (Yang Masih Harus Dibayar). Menampung nilai bunga yang sudah diakui sebagai beban tetapi tagihannya belum terbit."
    )

    journal_id = fields.Many2one(
        'account.journal',
        string="Jurnal Penyesuaian (Journal)",
        help="Buku harian tempat sistem mencatat jurnal penyesuaian bunga bulanan. Biasanya diisi dengan Jurnal Umum (Miscellaneous Operations)."
    )

    # ---- Leasing Header Fields (Manual Input) ----
    agreement_no = fields.Char(
        string='Agreement No.',
        tracking=True,
        help='The official contract number provided by the leasing company/dealer.',
    )
    bank_id = fields.Many2one(
        'res.partner',
        string='Bank',
        tracking=True,
        domain="[('is_company', '=', True)]",
        help='The financial institution or leasing company providing the credit.',
    )
    jenis_kredit = fields.Selection(
        selection=[
            ('conventional', 'Conventional'),
            ('syariah', 'Syariah'),
        ],
        string='Jenis Kredit',
        default='conventional',
        tracking=True,
        help='The type of credit facility.',
    )
    start_date_leasing = fields.Date(
        string='Leasing Start Date',
        tracking=True,
        help='The commencement date of the first installment.',
    )
    advarr = fields.Selection(
        selection=[
            ('in_advance_addm', 'In Advanced/ADDM'),
            ('in_arrears', 'In Arrears'),
        ],
        string='Advarr',
        tracking=True,
        help='Select advance type.',
    )
    payment_timing = fields.Selection(
        selection=[
            ('end_of_month', 'End of Month'),
            ('anniversary', 'Anniversary Date'),
            ('specific_date', 'Specific Date'),
        ],
        string='Payment',
        default='end_of_month',
        tracking=True,
        help='Defines when the monthly bill is generated.',
    )

    # ---- Vehicle Fields ----
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Vehicle',
        tracking=True,
        readonly=True,
        help='Select the vehicle related to this leasing.',
    )
    plate_number = fields.Char(
        string='Plate Number',
        related='vehicle_id.license_plate',
        readonly=True,
        store=True,
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        compute='_compute_analytic_account_id',
        store=True,
        readonly=True,
    )
    vehicle_brand = fields.Char(
        string='Merk',
        compute='_compute_vehicle_info',
        store=True,
    )
    vehicle_type = fields.Char(
        string='Type',
        compute='_compute_vehicle_info',
        store=True,
    )
    vehicle_variant = fields.Char(
        string='Varian',
    )
    vehicle_year = fields.Char(
        string='Tahun',
        compute='_compute_vehicle_info',
        store=True,
    )

    # ---- Auto-filled Financial Fields (from PO) ----
    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        compute='_compute_po_fields',
        store=True,
        readonly=False,
        help='The supplier (synchronized from the PO).',
    )
    po_number = fields.Char(
        string='PO Number',
        compute='_compute_po_fields',
        store=True,
        readonly=False,
        help='The reference number of the related PO.',
    )
    total_hutang = fields.Monetary(
        string='Total Hutang',
        compute='_compute_po_fields',
        store=True,
        readonly=False,
        currency_field='currency_id',
        help='The total debt amount (from the PO).',
    )
    harga_otr = fields.Monetary(
        string='Harga OTR',
        compute='_compute_po_fields',
        store=True,
        readonly=False,
        currency_field='currency_id',
        help='OTR price.',
    )
    down_payment_leasing = fields.Monetary(
        string='Down Payment',
        compute='_compute_po_fields',
        store=True,
        readonly=False,
        currency_field='currency_id',
        help='Down payment amount (from the PO).',
    )
    installment_amount = fields.Monetary(
        string='Installment',
        compute='_compute_po_fields',
        store=True,
        readonly=False,
        currency_field='currency_id',
        help='Fixed monthly installment amount.',
    )
    interest_rate_annual = fields.Float(
        string='Interest (%)',
        help='Annual interest rate percentage.',
        digits=(13,10)
    )
    loan_term_years = fields.Float(
        string='Loan Term',
        compute='_compute_loan_term_years',
        store=True,
        help='The loan duration converted from months into years.',
    )

    # ---- Task 2 & 3: Selection Compute Method & Header Fields ----
    compute_method = fields.Selection(
        selection=[
            ('effective', 'Bunga Efektif'),
            ('flat', 'Bunga Flat'),
        ],
        string='Compute Method',
        default='effective',
        required=True,
        tracking=True,
        help='Select interest calculation method: Effective or Flat.'
    )
    monthly_installment = fields.Monetary(
        string='Cicilan Per Bulan',
        currency_field='currency_id',
        tracking=True,
        help='Fixed monthly installment amount to be paid.'
    )
    total_installment_payment = fields.Monetary(
        string='Total Pembayaran Cicilan',
        currency_field='currency_id',
        compute='_compute_total_installment_payment',
        store=True,
        readonly=True,
        tracking=True,
        help='Total installment payments calculated automatically.'
    )
    saldo_pokok_hutang = fields.Monetary(
        string='Saldo Pokok Hutang',
        compute='_compute_saldo_pokok_hutang',
        currency_field='currency_id',
        store=True,
    )
    total_bunga = fields.Monetary(
        string='Total Bunga',
        compute='_compute_total_bunga',
        currency_field='currency_id',
        store=True,
    )
    remaining_loan = fields.Integer(
        string='Remaining Loan',
        compute='_compute_remaining_loan',
        store=True,
        help='Sisa durasi cicilan (bulan) yang belum terposting.'
    )

    @api.depends('total_hutang', 'monthly_installment')
    def _compute_saldo_pokok_hutang(self):
        for loan in self:
            loan.saldo_pokok_hutang = (loan.total_hutang or 0.0) - (loan.monthly_installment or 0.0)

    @api.depends('total_installment_payment', 'saldo_pokok_hutang')
    def _compute_total_bunga(self):
        for loan in self:
            loan.total_bunga = (loan.total_installment_payment or 0.0) - (loan.saldo_pokok_hutang or 0.0)

    @api.depends('duration', 'line_ids.vendor_bill_id.state')
    def _compute_remaining_loan(self):
        for loan in self:
            posted_count = len(loan.line_ids.filtered(lambda l: l.vendor_bill_id and l.vendor_bill_id.state == 'posted'))
            loan.remaining_loan = (loan.duration or 0) - posted_count

    @api.depends('monthly_installment', 'duration', 'line_ids', 'line_ids.payment')
    def _compute_total_installment_payment(self):
        for loan in self:
            if loan.line_ids and len(loan.line_ids) > 1:
                # Sum payments from installment 2 to N (excluding installment 1 DP)
                loan.total_installment_payment = sum(loan.line_ids[1:].mapped('payment'))
            elif loan.monthly_installment and loan.duration > 1:
                loan.total_installment_payment = loan.monthly_installment * (loan.duration - 1)
            else:
                loan.total_installment_payment = 0.0

    def action_compute_amortization_schedule(self):
        """
        Kalkulasi jadwal angsuran berdasarkan metode Bunga Efektif atau Bunga Flat.
        Dijalankan saat tombol Compute diklik.
        """
        from dateutil.relativedelta import relativedelta

        for loan in self:
            if loan.state != 'draft':
                raise UserError(_("Perhitungan ulang hanya dapat dilakukan pada status Draft."))

            duration = int(loan.duration) if loan.duration else 0
            if duration <= 0:
                # Fallback duration from loan_term if set, else raise
                duration = 12
                loan.duration = duration

            otr = loan.harga_otr or 0.0
            dp = loan.down_payment_leasing or 0.0
            cicilan_bulan = loan.monthly_installment or loan.installment_amount or 0.0
            rate_annual = (loan.interest_rate_annual or 0.0) / 100.0
            start_date = loan.start_date_leasing or loan.date or fields.Date.context_today(loan)

            pokok_hutang_awal = otr - dp if (otr > 0 and dp > 0 and otr > dp) else (loan.total_hutang or 0.0)
            
            # If monthly_installment is empty, calculate automatically
            if not cicilan_bulan and duration > 0 and pokok_hutang_awal > 0:
                if rate_annual > 0:
                    bunga_per_bulan = (pokok_hutang_awal * rate_annual) / 12.0
                    pokok_per_bulan = pokok_hutang_awal / duration
                    cicilan_bulan = round(pokok_per_bulan + bunga_per_bulan, 2)
                else:
                    cicilan_bulan = round(pokok_hutang_awal / duration, 2)

            loan.line_ids.unlink()
            lines_vals = []
            current_date = start_date

            # Angsuran Ke-1 (Masuk ke dalam DP / Cicilan 1)
            pokok_1 = min(pokok_hutang_awal, cicilan_bulan) if cicilan_bulan > 0 else pokok_hutang_awal
            bunga_1 = 0.0
            total_1 = cicilan_bulan
            
            saldo_pokok_1 = max(0.0, pokok_hutang_awal - pokok_1)
            saldo_pokok_running = saldo_pokok_1

            # Line 1 (Angsuran Ke-1)
            lines_vals.append({
                'loan_id': loan.id,
                'date': current_date,
                'principal': pokok_1,
                'interest': bunga_1,
                'payment': total_1,
            })

            # Angsuran Ke-2 s/d Ke-N
            first_payment_date = getattr(loan, 'first_payment_date', False)
            for i in range(2, duration + 1):
                if i == 2 and first_payment_date:
                    current_date = first_payment_date
                elif first_payment_date:
                    current_date = first_payment_date + relativedelta(months=i-2)
                elif loan.payment_timing == 'end_of_month':
                    current_date = start_date + relativedelta(months=i-1, day=31)
                else:
                    # Anniversary date: keep exact day of start_date
                    current_date = start_date + relativedelta(months=i-1)
                
                if loan.compute_method == 'flat':
                    bunga_i = round((saldo_pokok_1 * rate_annual) / 12.0, 2)
                    pokok_i = cicilan_bulan - bunga_i
                else: # 'effective'
                    bunga_i = round(saldo_pokok_running * (rate_annual / 12.0), 2)
                    pokok_i = cicilan_bulan - bunga_i

                total_i = cicilan_bulan
                if i == duration:
                    pokok_i = saldo_pokok_running
                    if loan.compute_method == 'flat':
                        bunga_i = round((saldo_pokok_1 * rate_annual) / 12.0, 2)
                    else:
                        bunga_i = round(saldo_pokok_running * (rate_annual / 12.0), 2)
                    total_i = pokok_i + bunga_i

                saldo_pokok_running = max(0.0, saldo_pokok_running - pokok_i)

                lines_vals.append({
                    'loan_id': loan.id,
                    'date': current_date,
                    'principal': pokok_i,
                    'interest': bunga_i,
                    'payment': total_i,
                })

            self.env['account.loan.line'].create(lines_vals)

            loan.write({
                'monthly_installment': cicilan_bulan,
                'amount_borrowed': pokok_hutang_awal,
            })
            loan._compute_total_installment_payment()

        return True

    @api.onchange('total_hutang', 'interest_rate_annual', 'start_date_leasing')
    def _onchange_leasing_sync_standard(self):
        for loan in self:
            loan.amount_borrowed = loan.total_hutang
            loan.interest = loan.interest_rate_annual
            if loan.start_date_leasing:
                loan.date = loan.start_date_leasing

    # ---- Methods ----
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'New' or vals.get('name') == 'New Leasing':
                vals['name'] = self.env['ir.sequence'].next_by_code('account.loan.leasing') or 'New Leasing'
        return super().create(vals_list)

    @api.depends('vehicle_id', 'vehicle_id.brand_id', 'vehicle_id.model_id', 'vehicle_id.model_year')
    def _compute_vehicle_info(self):
        for loan in self:
            if loan.vehicle_id:
                loan.vehicle_brand = loan.vehicle_id.brand_id.name if loan.vehicle_id.brand_id else ''
                loan.vehicle_type = loan.vehicle_id.model_id.name if loan.vehicle_id.model_id else ''
                loan.vehicle_year = loan.vehicle_id.model_year or ''
            else:
                loan.vehicle_brand = ''
                loan.vehicle_type = ''
                loan.vehicle_year = ''

    @api.depends('vehicle_id', 'vehicle_id.analytic_account_id')
    def _compute_analytic_account_id(self):
        for loan in self:
            if loan.vehicle_id and hasattr(loan.vehicle_id, 'analytic_account_id') and loan.vehicle_id.analytic_account_id:
                loan.analytic_account_id = loan.vehicle_id.analytic_account_id.id
            else:
                loan.analytic_account_id = False

    def action_open_payment_wizard(self):
        self.ensure_one()
        unpaid_lines = self.line_ids.filtered(lambda l: not l.vendor_bill_id)
        if not unpaid_lines:
            raise UserError(_("Semua angsuran sudah lunas dibayar."))
            
        default_line_ids = [(0, 0, {
            'loan_line_id': line.id,
            'is_selected': False,
        }) for line in unpaid_lines]

        return {
            'name': _('Pay Installments'),
            'type': 'ir.actions.act_window',
            'res_model': 'leasing.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_loan_id': self.id,
                'default_line_ids': default_line_ids,
            }
        }

    @api.depends('purchase_order_id')
    def _compute_po_fields(self):
        for loan in self:
            po = loan.purchase_order_id
            if po:
                loan.po_number = po.name
                
                # Vendor autofill dari Leasing Partner sesuai instruksi
                if hasattr(po, 'leasing_partner_id') and po.leasing_partner_id:
                    loan.vendor_id = po.leasing_partner_id
                else:
                    loan.vendor_id = False
                    
                loan.total_hutang = po.leasing_debt_balance if hasattr(po, 'leasing_debt_balance') else 0.0
                loan.amount_borrowed = loan.total_hutang
                loan.harga_otr = po.amount_total
                loan.down_payment_leasing = po.down_payment_amount if hasattr(po, 'down_payment_amount') else 0.0
                loan.installment_amount = po.first_installment if hasattr(po, 'first_installment') else 0.0
            else:
                if not loan.vendor_id:
                    loan.vendor_id = False
                if not loan.po_number:
                    loan.po_number = ''
                if not loan.total_hutang:
                    loan.total_hutang = 0.0
                loan.harga_otr = 0.0
                if not loan.down_payment_leasing:
                    loan.down_payment_leasing = 0.0
                loan.installment_amount = 0.0

    @api.depends('duration')
    def _compute_loan_term_years(self):
        for loan in self:
            loan.loan_term_years = loan.duration / 12.0 if loan.duration else 0.0

    # ---- Action Methods ----

    def action_generate_vendor_bill(self):
        """Generate vendor bills for all unpaid loan lines that are due."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        lines_to_bill = self.line_ids.filtered(
            lambda l: l.date and l.date <= today and not l.vendor_bill_id
        )
        if not lines_to_bill:
            raise UserError(_("No due loan lines without a vendor bill found."))

        bills = self.env['account.move']
        for line in lines_to_bill:
            bill = line._generate_vendor_bill()
            if bill:
                bills |= bill

        if bills:
            if len(bills) == 1:
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Vendor Bill'),
                    'res_model': 'account.move',
                    'res_id': bills.id,
                    'view_mode': 'form',
                    'target': 'current',
                }
            return {
                'type': 'ir.actions.act_window',
                'name': _('Vendor Bills'),
                'res_model': 'account.move',
                'view_mode': 'list,form',
                'domain': [('id', 'in', bills.ids)],
                'target': 'current',
            }

    def action_open_compute_wizard(self):
        """Override to bypass the wizard and compute directly."""
        for loan in self:
            if loan.state != 'draft':
                raise UserError(_("Perhitungan ulang hanya dapat dilakukan pada status Draft."))
            loan.action_compute_amortization_schedule()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_confirm(self):
        """
        Override action_confirm to auto-adjust the last line's principal and bypass
        standard Odoo journal entry generation.
        """
        for loan in self:
            if loan.state == 'draft':
                if not loan.line_ids:
                    raise UserError(_("Silakan klik tombol 'Compute' terlebih dahulu untuk membuat jadwal angsuran sebelum Confirm."))
                if not loan.journal_id:
                    raise UserError(_("Jurnal penyesuaian (Journal) harus diisi terlebih dahulu."))
                if not loan.long_term_account_id or not loan.short_term_account_id or not loan.expense_account_id or not loan.accrued_interest_account_id:
                    raise UserError(_("Konfigurasi akun-akun hutang (Jangka Panjang, Jangka Pendek, Beban Bunga, dan Hutang Bunga Sementara) harus diisi terlebih dahulu pada tab Configuration."))

                if not loan.vehicle_id:
                    raise UserError(_("Vehicle harus terisi sebelum Leasing bisa di-Confirm."))
                if not loan.analytic_account_id:
                    raise UserError(_("Analytic Account harus terisi (didapat otomatis dari data Vehicle) sebelum Leasing bisa di-Confirm."))

                total_principal = sum(loan.line_ids.mapped('principal'))
                diff = loan.amount_borrowed - total_principal
                # If there's a difference, adjust the last line
                if abs(diff) > 0.001:
                    last_line = loan.line_ids.sorted('date')[-1]
                    last_line.principal += diff
                
                # Directly set state to running instead of calling super()
                loan.write({'state': 'running'})
                
        return True

    @api.depends('line_ids.vendor_bill_id.state', 'line_ids.monthly_adjustment_move_id.state')
    def _compute_nb_posted_entries(self):
        for loan in self:
            posted_move_ids = set()
            for line in loan.line_ids:
                if line.vendor_bill_id and line.vendor_bill_id.state == 'posted':
                    posted_move_ids.add(line.vendor_bill_id.id)
                if line.monthly_adjustment_move_id and line.monthly_adjustment_move_id.state == 'posted':
                    posted_move_ids.add(line.monthly_adjustment_move_id.id)
            loan.nb_posted_entries = len(posted_move_ids)

    def action_open_loan_entries(self):
        self.ensure_one()
        move_ids = []
        for line in self.line_ids:
            if line.vendor_bill_id:
                move_ids.append(line.vendor_bill_id.id)
            if line.monthly_adjustment_move_id:
                move_ids.append(line.monthly_adjustment_move_id.id)
                
        return {
            'name': _('Loan Entries'),
            'view_mode': 'list,form',
            'res_model': 'account.move',
            'views': [(self.env.ref('account_loans.account_loan_view_account_move_list_view').id, 'list'), (False, 'form')],
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', move_ids)],
        }



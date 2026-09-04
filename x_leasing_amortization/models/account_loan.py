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
        help='Select the vehicle related to this leasing.',
    )
    plate_number = fields.Char(
        string='Plate Number',
        related='vehicle_id.license_plate',
        readonly=True,
        store=True,
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
    )
    loan_term_years = fields.Float(
        string='Loan Term',
        compute='_compute_loan_term_years',
        store=True,
        help='The loan duration converted from months into years.',
    )

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
                    
                qty = max(1.0, float(sum(po.order_line.mapped('product_qty'))))
                    
                loan.total_hutang = (po.leasing_debt_balance / qty) if hasattr(po, 'leasing_debt_balance') else 0.0
                loan.amount_borrowed = loan.total_hutang
                loan.harga_otr = (po.amount_total / qty)
                loan.down_payment_leasing = (po.down_payment_amount / qty) if hasattr(po, 'down_payment_amount') else 0.0
                loan.installment_amount = (po.first_installment / qty) if hasattr(po, 'first_installment') else 0.0
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
        """Override to ensure leasing custom fields are correctly passed to the wizard."""
        res = super(AccountLoan, self).action_open_compute_wizard()
        if isinstance(res, dict) and res.get('res_model') == 'account.loan.compute.wizard' and res.get('res_id'):
            wizard = self.env['account.loan.compute.wizard'].browse(res['res_id'])
            update_vals = {}
            if hasattr(self, 'total_hutang') and self.total_hutang:
                update_vals['loan_amount'] = self.total_hutang
            if hasattr(self, 'interest_rate_annual') and self.interest_rate_annual:
                update_vals['interest_rate'] = self.interest_rate_annual
            elif hasattr(self, 'interest') and self.interest:
                update_vals['interest_rate'] = self.interest
            if hasattr(self, 'duration') and self.duration:
                update_vals['loan_term'] = int(round(self.duration / 12.0))
            if hasattr(self, 'start_date_leasing') and self.start_date_leasing:
                update_vals['start_date'] = self.start_date_leasing
            
            if update_vals:
                wizard.write(update_vals)
        return res

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

class AccountLoanComputeWizard(models.TransientModel):
    _inherit = 'account.loan.compute.wizard'

    @api.model
    def default_get(self, fields_list):
        res = super(AccountLoanComputeWizard, self).default_get(fields_list)
        active_id = self.env.context.get('active_id')
        active_model = self.env.context.get('active_model')
        if active_id and active_model == 'account.loan':
            loan = self.env['account.loan'].browse(active_id)
            if hasattr(loan, 'total_hutang') and loan.total_hutang:
                res['loan_amount'] = loan.total_hutang
            
            # Use interest_rate_annual for the wizard's interest_rate
            if hasattr(loan, 'interest_rate_annual') and loan.interest_rate_annual:
                res['interest_rate'] = loan.interest_rate_annual
            elif hasattr(loan, 'interest') and loan.interest:
                res['interest_rate'] = loan.interest
                
            if hasattr(loan, 'start_date_leasing') and loan.start_date_leasing:
                res['start_date'] = loan.start_date_leasing
            
            # Map Duration (months) to Loan Term (years)
            if hasattr(loan, 'duration') and loan.duration:
                # loan_term is an integer field representing years
                res['loan_term'] = int(round(loan.duration / 12.0))
        return res

# -*- coding: utf-8 -*-
import math
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class RpcDocument(models.Model):
    _name = 'rpc.document'
    _description = 'Rental Profit Calculation Document'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'
    _rec_name = 'name'

    # ─────────────────────────────────────────────
    # HEADER FIELDS
    # ─────────────────────────────────────────────
    name = fields.Char(
        string='Nomor RPC', readonly=True, copy=False,
        default='New', tracking=True
    )
    creation_date = fields.Date(
        string='Tanggal Pembuatan', default=fields.Date.today,
        readonly=True
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='company_id.currency_id', store=True, readonly=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('procurement_done', 'Procurement Done'),
        ('operation_done', 'Operation Done'),
        ('finance_done', 'Finance Done'),
        ('approved', 'Approved'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)

    is_template = fields.Boolean(string='Template', default=False,
                                  help='Jadikan dokumen ini sebagai template untuk duplikasi')

    marketing_id = fields.Many2one(
        'hr.employee', string='Marketing',
        default=lambda self: self._default_marketing(),
        tracking=True
    )
    pembuat_rpc_id = fields.Many2one(
        'hr.employee', string='Pembuat RPC',
        default=lambda self: self._default_marketing(),
        readonly=True
    )
    partner_id = fields.Many2one(
        'res.partner', string='Nama Klien',
        required=True, tracking=True,
        domain=[('customer_rank', '>', 0)]
    )
    crm_lead_id = fields.Many2one(
        'crm.lead', string='CRM Opportunity',
        domain="[('partner_id', '=', partner_id)]"
    )
    reference = fields.Char(string='Reference')

    # Dropdowns from rpc.parameter
    type_of_klien_id = fields.Many2one(
        'rpc.parameter', string='Type of Klien', required=True,
        domain=[('parameter_type', '=', 'type_of_klien')]
    )
    jenis_transaksi_id = fields.Many2one(
        'rpc.parameter', string='Jenis Transaksi', required=True,
        domain=[('parameter_type', '=', 'jenis_transaksi')]
    )
    tujuan_id = fields.Many2one(
        'rpc.parameter', string='Tujuan', required=True,
        domain=[('parameter_type', '=', 'tujuan')]
    )
    sumber_id = fields.Many2one(
        'rpc.parameter', string='Sumber', required=True,
        domain=[('parameter_type', '=', 'sumber')]
    )
    sumber_daya_id = fields.Many2one(
        'rpc.parameter', string='Sumber Daya', required=True,
        domain=[('parameter_type', '=', 'sumber_daya')]
    )
    jenis_kendaraan_id = fields.Many2one(
        'rpc.parameter', string='Jenis Kendaraan', required=True,
        domain=[('parameter_type', '=', 'jenis_kendaraan')]
    )
    penggunaan_kendaraan_id = fields.Many2one(
        'rpc.parameter', string='Penggunaan Kendaraan',
        domain=[('parameter_type', '=', 'penggunaan_kendaraan')]
    )
    pemakaian_id = fields.Many2one(
        'rpc.parameter', string='Pemakaian', required=True,
        domain=[('parameter_type', '=', 'pemakaian')]
    )
    merek_id = fields.Many2one(
        'rpc.parameter', string='Merek', required=True,
        domain=[('parameter_type', '=', 'merek')]
    )
    type_kendaraan = fields.Char(string='Type', help='Tipe kendaraan - free text')
    tahun_kendaraan = fields.Integer(string='Tahun')
    provinsi_id = fields.Many2one('rpc.provinsi', string='Provinsi', required=True)
    kota_id = fields.Many2one(
        'rpc.kota', string='Kota', required=True,
        domain="[('provinsi_id', '=', provinsi_id)]"
    )
    wilayah_id = fields.Many2one(
        'rpc.wilayah', string='Wilayah',
        related='provinsi_id.wilayah_id', store=True, readonly=True
    )
    masa_sewa = fields.Integer(string='Masa Sewa (Bulan)', required=True)
    masa_sewa_buffer = fields.Integer(string='Masa Sewa Buffer (Bulan)')
    jumlah_unit = fields.Integer(string='Jumlah Unit', required=True, default=1)

    # ─────────────────────────────────────────────
    # SECTION MARKETING
    # ─────────────────────────────────────────────
    hok = fields.Selection([
        ('yes', 'YES'),
        ('no', 'NO'),
    ], string='HOK', required=True, default='no')
    resale_value_pct = fields.Float(
        string='Resale Value (%)', digits=(5, 4),
        help='Mandatory jika HOK = YES'
    )
    basis_otr = fields.Selection([
        ('gross_otr', 'Gross OTR'),
        ('net_otr', 'Net OTR'),
    ], string='Basis OTR', help='Mandatory jika HOK = YES')

    sewa_per_bulan_batas_atas = fields.Monetary(
        string='Sewa/Bulan - Batas Atas', currency_field='currency_id', required=True
    )
    sewa_per_bulan_batas_bawah = fields.Monetary(
        string='Sewa/Bulan - Batas Bawah', currency_field='currency_id', required=True
    )

    ruu_gross = fields.Float(
        string='RUU Gross (%)', compute='_compute_ruu', store=True, digits=(5, 4)
    )
    ruu_netto = fields.Float(
        string='RUU Netto (%)', compute='_compute_ruu', store=True, digits=(5, 4)
    )
    ruu_gross_batas_bawah = fields.Float(
        string='RUU Gross Batas Bawah (%)', compute='_compute_ruu', store=True, digits=(5, 4)
    )
    ruu_netto_batas_bawah = fields.Float(
        string='RUU Netto Batas Bawah (%)', compute='_compute_ruu', store=True, digits=(5, 4)
    )

    # Fasilitas/Fitur Sewa
    management_fee = fields.Monetary(
        string='Management Fee',
        currency_field='currency_id',
        help='Management fee per unit.',
    )
    free_own_risk = fields.Monetary(
        string='Free Own Risk',
        currency_field='currency_id',
        help='Free own risk per tahun.',
    )
    bank_garansi_deposit = fields.Monetary(
        string='Bank Garansi/Deposit',
        currency_field='currency_id',
        help='Bank garansi atau deposit satu kali.',
    )
    asuransi_jiwa_pa = fields.Monetary(
        string='Asuransi Jiwa, PA',
        currency_field='currency_id',
        help='Asuransi jiwa atau personal accident selama tenor.',
    )

    term_of_payment_hari = fields.Integer(string='Terms of Payment (TOP)', required=True)
    term_of_payment_due = fields.Selection([
        ('addb', 'Di Belakang'),
        ('addm', 'Di Muka'),
    ], string='Posisi Pembayaran', required=True)

    # Biaya Marketing dan Komisi
    pic_internal = fields.Monetary(string='PIC Internal (per Unit/Bulan)', currency_field='currency_id')
    infrastruktur = fields.Monetary(string='Infrastruktur (Lumpsum)', currency_field='currency_id')
    komisi_proyek = fields.Monetary(string='Komisi Proyek (Lumpsum)', currency_field='currency_id')
    lainnya_marketing = fields.Monetary(string='Lainnya (per Bulan)', currency_field='currency_id')
    total_biaya_marketing = fields.Monetary(
        string='Total Biaya Marketing dan Komisi',
        compute='_compute_total_biaya_marketing', store=True, currency_field='currency_id'
    )

    # Special Request Lines
    special_request_ids = fields.One2many(
        'rpc.document.special.request.line', 'document_id',
        string='Special Request Kendaraan'
    )

    # ─────────────────────────────────────────────
    # SECTION PROCUREMENT
    # ─────────────────────────────────────────────
    def _default_purchase_line_values(self):
        return [
            {'sequence': 10, 'line_type': 'harga_otr', 'description': 'HARGA OTR'},
            {'sequence': 20, 'line_type': 'discount', 'description': 'DISCOUNT'},
            {'sequence': 30, 'line_type': 'cashback', 'description': 'CASHBACK'},
            {'sequence': 40, 'line_type': 'special_req_1', 'description': 'SPECIAL REQUEST 1'},
            {'sequence': 50, 'line_type': 'special_req_2', 'description': 'SPECIAL REQUEST 2'},
            {'sequence': 60, 'line_type': 'special_req_3', 'description': 'SPECIAL REQUEST 3'},
            {'sequence': 70, 'line_type': 'special_req_4', 'description': 'SPECIAL REQUEST 4'},
            {'sequence': 80, 'line_type': 'special_req_5', 'description': 'SPECIAL REQUEST 5'},
            {'sequence': 90, 'line_type': 'biaya_ekspedisi', 'description': 'BIAYA EKSPEDISI/PENGIRIMAN'},
        ]

    purchase_line_ids = fields.One2many(
        'rpc.document.purchase.line', 'document_id',
        string='Perincian Pembelian'
    )
    dealer_line_ids = fields.One2many(
        'rpc.document.dealer.line', 'document_id',
        string='Dealer Information'
    )
    harga_otr = fields.Monetary(string='Harga OTR (Standard OTR)', currency_field='currency_id')
    discount = fields.Monetary(string='Discount', currency_field='currency_id')
    discount_dikapitalisasi = fields.Selection([
        ('yes', 'YES'), ('no', 'NO')
    ], string='Discount Dikapitalisasi', default='no')
    cashback = fields.Monetary(string='Cashback', currency_field='currency_id')
    cashback_dikapitalisasi = fields.Selection([
        ('yes', 'YES'), ('no', 'NO')
    ], string='Cashback Dikapitalisasi', default='no')

    # Special Request 1-5 Procurement
    special_req_1_desc = fields.Char(string='Special Request 1 - Deskripsi')
    special_req_1_amount = fields.Monetary(string='Special Request 1 - Amount', currency_field='currency_id')
    special_req_1_kapitalisasi = fields.Selection([('yes', 'YES'), ('no', 'NO')], string='SR1 Dikapitalisasi', default='no')

    special_req_2_desc = fields.Char(string='Special Request 2 - Deskripsi')
    special_req_2_amount = fields.Monetary(string='Special Request 2 - Amount', currency_field='currency_id')
    special_req_2_kapitalisasi = fields.Selection([('yes', 'YES'), ('no', 'NO')], string='SR2 Dikapitalisasi', default='no')

    special_req_3_desc = fields.Char(string='Special Request 3 - Deskripsi')
    special_req_3_amount = fields.Monetary(string='Special Request 3 - Amount', currency_field='currency_id')
    special_req_3_kapitalisasi = fields.Selection([('yes', 'YES'), ('no', 'NO')], string='SR3 Dikapitalisasi', default='no')

    special_req_4_desc = fields.Char(string='Special Request 4 - Deskripsi')
    special_req_4_amount = fields.Monetary(string='Special Request 4 - Amount', currency_field='currency_id')
    special_req_4_kapitalisasi = fields.Selection([('yes', 'YES'), ('no', 'NO')], string='SR4 Dikapitalisasi', default='no')

    special_req_5_desc = fields.Char(string='Special Request 5 - Deskripsi')
    special_req_5_amount = fields.Monetary(string='Special Request 5 - Amount', currency_field='currency_id')
    special_req_5_kapitalisasi = fields.Selection([('yes', 'YES'), ('no', 'NO')], string='SR5 Dikapitalisasi', default='no')

    biaya_ekspedisi = fields.Monetary(string='Biaya Ekspedisi/Pengiriman', currency_field='currency_id')
    biaya_ekspedisi_dikapitalisasi = fields.Selection([
        ('yes', 'YES'), ('no', 'NO')
    ], string='Biaya Ekspedisi Dikapitalisasi', default='no')

    otr_final = fields.Monetary(
        string='OTR Final', compute='_compute_otr', store=True, currency_field='currency_id'
    )
    otr_leasing = fields.Monetary(
        string='OTR Leasing', compute='_compute_otr', store=True, currency_field='currency_id'
    )
    otr_asuransi = fields.Monetary(
        string='OTR Asuransi', compute='_compute_otr', store=True, currency_field='currency_id'
    )

    # ─────────────────────────────────────────────
    # SECTION OPERATION
    # ─────────────────────────────────────────────
    biaya_towing = fields.Monetary(string='Biaya Towing (per Tahun/Unit)', currency_field='currency_id')
    replacement_car_qty = fields.Integer(string='Replacement Car Quantity')
    replacement_car_ratio = fields.Float(
        string='Replacement Car Ratio (%)', compute='_compute_replacement_ratio',
        store=True, digits=(5, 4)
    )

    # STNK Lines (max 5)
    stnk_line_ids = fields.One2many(
        'rpc.document.stnk.line', 'document_id',
        string='Estimasi Biaya STNK'
    )

    # Service Lines (max 5)
    service_line_ids = fields.One2many(
        'rpc.document.service.line', 'document_id',
        string='Estimasi Biaya Service'
    )

    # Resale Value
    umur_saat_dispose = fields.Integer(
        string='Umur Saat Dispose (Bulan)',
        compute='_compute_umur_saat_dispose', store=True
    )
    resale_value_rate = fields.Float(string='Resale Value Rate (%)', digits=(5, 4))
    resale_price = fields.Monetary(
        string='Resale Price', compute='_compute_resale', store=True, currency_field='currency_id'
    )
    total_useful_life = fields.Integer(
        string='Total Useful Life (Bulan)',
        default=96,
        help='Default 96 bulan (8 tahun). Bisa dikonfigurasi.'
    )
    total_accum_saat_dispose = fields.Monetary(
        string='Total Accum Saat Dispose',
        compute='_compute_resale', store=True, currency_field='currency_id'
    )
    nilai_buku = fields.Monetary(
        string='Nilai Buku', compute='_compute_resale', store=True, currency_field='currency_id'
    )
    sisa_nilai_buku = fields.Monetary(
        string='Sisa Nilai Buku (Regular-Used)', currency_field='currency_id',
        help='Diisi jika Jenis Transaksi = Regular-Used'
    )
    catatan_rv = fields.Char(
        string='Catatan RV', compute='_compute_catatan_rv', store=True
    )
    estimasi_loss_nilai_buku = fields.Monetary(
        string='Estimasi Loss atas Nilai Buku',
        compute='_compute_catatan_rv',
        store=True,
        currency_field='currency_id',
        help='Selisih negatif antara Resale Price dan Nilai Buku.',
    )

    # ─────────────────────────────────────────────
    # SECTION FINANCE
    # ─────────────────────────────────────────────
    leasing_bank_id = fields.Many2one(
        'rpc.parameter', string='Leasing/Bank',
        domain=[('parameter_type', '=', 'leasing_bank')]
    )
    masa_kredit = fields.Integer(string='Masa Kredit (Bulan)')
    down_payment_pct = fields.Float(string='Down Payment (% dari OTR Leasing)', digits=(5, 4))
    bunga_pct = fields.Float(string='Bunga (% flat per Tahun)', digits=(5, 4))
    jenis_angsuran_id = fields.Many2one(
        'rpc.parameter', string='Jenis Angsuran',
        domain=[('parameter_type', '=', 'jenis_angsuran')]
    )
    provisi_admin_pct = fields.Float(string='Provisi & Admin (%)', digits=(5, 4))
    fidusia = fields.Monetary(string='Fidusia (di muka)', currency_field='currency_id')
    penalti_pct = fields.Float(string='Penalti (% dari sisa Outstanding)', digits=(5, 4))

    opex_pusat_pct = fields.Float(string='Opex Pusat (% per tahun dari OTR Final)', digits=(5, 4))
    cost_of_fund_pct = fields.Float(string='Cost of Fund (% dari Funding)', digits=(5, 4))

    # Terms of Payment Finance (copied from Marketing)
    finance_term_of_payment_hari = fields.Integer(
        string='Terms of Payment (TOP)',
        compute='_compute_finance_top', store=True
    )
    finance_term_of_payment_due = fields.Selection([
        ('addb', 'Di Belakang'),
        ('addm', 'Di Muka'),
    ], string='Posisi Pembayaran',
        compute='_compute_finance_top', store=True
    )
    pokok_hutang = fields.Monetary(
        string='Pokok Hutang', compute='_compute_finance_amounts',
        store=True, currency_field='currency_id'
    )
    down_payment_amount = fields.Monetary(
        string='Down Payment', compute='_compute_finance_amounts',
        store=True, currency_field='currency_id'
    )
    angsuran_per_bulan = fields.Monetary(
        string='Angsuran / Bulan', compute='_compute_finance_amounts',
        store=True, currency_field='currency_id'
    )
    total_downpayment = fields.Monetary(
        string='Total Downpayment', compute='_compute_finance_amounts',
        store=True, currency_field='currency_id'
    )
    insurance_wilayah = fields.Char(string='Wilayah')
    insurance_group_otr = fields.Char(string='Group OTR')
    insurance_type = fields.Selection([
        ('batas_atas', 'Batas Atas'),
        ('batas_bawah', 'Batas Bawah'),
        ('crs', 'CRS'),
    ], string='Asuransi Type')
    insurance_line_ids = fields.One2many(
        'rpc.document.insurance.line', 'document_id',
        string='Asuransi'
    )
    finance_unit_line_ids = fields.One2many(
        'rpc.document.finance.line', 'document_id',
        string='Perhitungan / Unit',
        domain=[('table_type', '=', 'unit')]
    )
    finance_cashflow_line_ids = fields.One2many(
        'rpc.document.finance.line', 'document_id',
        string='Cashflow',
        domain=[('table_type', '=', 'cashflow')]
    )
    existing_unit = fields.Integer(string='Existing Unit')
    menjadi_unit = fields.Float(
        string='Menjadi Unit', compute='_compute_consolidation',
        store=True, digits=(16, 2)
    )
    otr_existing = fields.Monetary(string='OTR (Existing)', currency_field='currency_id')
    otr_menjadi = fields.Monetary(
        string='OTR (Menjadi)', compute='_compute_consolidation',
        store=True, currency_field='currency_id'
    )
    ruu_existing = fields.Float(string='RUU Existing (%)', digits=(5, 4))
    ruu_konsolidasi = fields.Float(string='RUU Konsolidasi (%)', digits=(5, 4))
    buffer_hok = fields.Float(string='Buffer HOK (%)', digits=(5, 4))

    # ─────────────────────────────────────────────
    # COMPUTED FIELDS
    # ─────────────────────────────────────────────

    def _default_marketing(self):
        return self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )

    def _check_required_fields(self, fields_to_check):
        for rec in self:
            missing = []
            for field_name in fields_to_check:
                value = rec[field_name]
                if not value:
                    missing.append(rec._fields[field_name].string)
            if missing:
                raise UserError(_('Mohon lengkapi field wajib berikut: %s') % ', '.join(missing))

    def _check_positive_fields(self, fields_to_check):
        for rec in self:
            invalid = []
            for field_name in fields_to_check:
                if rec[field_name] <= 0:
                    invalid.append(rec._fields[field_name].string)
            if invalid:
                raise UserError(_('Field berikut harus lebih besar dari 0: %s') % ', '.join(invalid))

    @api.onchange('hok')
    def _onchange_hok(self):
        if self.hok == 'no':
            self.resale_value_pct = 0.0
            self.basis_otr = False

    @api.depends('term_of_payment_hari', 'term_of_payment_due')
    def _compute_finance_top(self):
        for rec in self:
            rec.finance_term_of_payment_hari = rec.term_of_payment_hari
            rec.finance_term_of_payment_due = rec.term_of_payment_due

    @api.depends('otr_leasing', 'down_payment_pct', 'bunga_pct', 'masa_kredit', 'fidusia')
    def _compute_finance_amounts(self):
        for rec in self:
            # Percentage widgets store 10% as 0.10 and 5.25% as 0.0525.
            rec.down_payment_amount = rec.down_payment_pct * rec.otr_leasing
            rec.pokok_hutang = (1.0 - rec.down_payment_pct) * rec.otr_leasing
            rec.angsuran_per_bulan = (
                (
                    (rec.bunga_pct / 12.0 * rec.masa_kredit + 1.0)
                    * rec.pokok_hutang
                ) / rec.masa_kredit
                if rec.masa_kredit else 0.0
            )
            rec.total_downpayment = rec.down_payment_amount + rec.fidusia

    @api.depends('existing_unit', 'jumlah_unit', 'otr_existing', 'otr_final')
    def _compute_consolidation(self):
        for rec in self:
            rec.menjadi_unit = rec.existing_unit + rec.jumlah_unit
            rec.otr_menjadi = rec.otr_existing + (rec.otr_final * rec.jumlah_unit)

    @api.depends(
        'harga_otr', 'discount', 'cashback',
        'special_req_1_amount', 'special_req_2_amount',
        'special_req_3_amount', 'special_req_4_amount',
        'special_req_5_amount', 'biaya_ekspedisi',
        'purchase_line_ids.amount',
        'purchase_line_ids.line_type',
    )
    def _compute_otr(self):
        for rec in self:
            if rec.purchase_line_ids:
                lines = {line.line_type: line for line in rec.purchase_line_ids}
                harga_otr = lines.get('harga_otr').amount if lines.get('harga_otr') else 0.0
                discount = lines.get('discount').amount if lines.get('discount') else 0.0
                cashback = lines.get('cashback').amount if lines.get('cashback') else 0.0
                biaya_ekspedisi = lines.get('biaya_ekspedisi').amount if lines.get('biaya_ekspedisi') else 0.0
                special_request_lines = [
                    line for line in rec.purchase_line_ids
                    if line.line_type and line.line_type.startswith('special_req_')
                ]
                total_sr = sum(line.amount for line in special_request_lines)

                # OTR Final = Harga OTR - Discount - Cashback + biaya lain.
                rec.otr_final = harga_otr - discount - cashback + total_sr + biaya_ekspedisi
                # OTR Leasing hanya memperhitungkan Harga OTR dan Discount.
                rec.otr_leasing = harga_otr - discount
                # OTR Asuransi selalu sama dengan OTR Leasing.
                rec.otr_asuransi = rec.otr_leasing
                continue

            total_sr = (
                rec.special_req_1_amount + rec.special_req_2_amount +
                rec.special_req_3_amount + rec.special_req_4_amount +
                rec.special_req_5_amount
            )
            # OTR Final = Harga OTR - Discount - Cashback + biaya lain.
            rec.otr_final = (
                rec.harga_otr - rec.discount - rec.cashback +
                total_sr + rec.biaya_ekspedisi
            )
            # OTR Leasing hanya memperhitungkan Harga OTR dan Discount.
            rec.otr_leasing = rec.harga_otr - rec.discount
            # OTR Asuransi selalu sama dengan OTR Leasing.
            rec.otr_asuransi = rec.otr_leasing

    @api.depends(
        'sewa_per_bulan_batas_atas', 'sewa_per_bulan_batas_bawah',
        'otr_final', 'total_biaya_marketing', 'masa_sewa', 'jumlah_unit'
    )
    def _compute_ruu(self):
        for rec in self:
            if rec.otr_final:
                rec.ruu_gross = (rec.sewa_per_bulan_batas_atas / rec.otr_final) * 100.0
                rec.ruu_gross_batas_bawah = (rec.sewa_per_bulan_batas_bawah / rec.otr_final) * 100.0
                if rec.masa_sewa and rec.jumlah_unit:
                    biaya_per_unit_bulan = rec.total_biaya_marketing / (rec.masa_sewa * rec.jumlah_unit) if (rec.masa_sewa * rec.jumlah_unit) else 0.0
                    rec.ruu_netto = ((rec.sewa_per_bulan_batas_atas - biaya_per_unit_bulan) / rec.otr_final) * 100.0
                    rec.ruu_netto_batas_bawah = ((rec.sewa_per_bulan_batas_bawah - biaya_per_unit_bulan) / rec.otr_final) * 100.0
                else:
                    rec.ruu_netto = 0.0
                    rec.ruu_netto_batas_bawah = 0.0
            else:
                rec.ruu_gross = 0.0
                rec.ruu_netto = 0.0
                rec.ruu_gross_batas_bawah = 0.0
                rec.ruu_netto_batas_bawah = 0.0

    @api.depends(
        'pic_internal', 'masa_sewa', 'jumlah_unit',
        'infrastruktur', 'komisi_proyek', 'lainnya_marketing'
    )
    def _compute_total_biaya_marketing(self):
        for rec in self:
            rec.total_biaya_marketing = (
                rec.pic_internal * rec.masa_sewa * rec.jumlah_unit +
                rec.infrastruktur + rec.komisi_proyek +
                rec.lainnya_marketing * rec.masa_sewa
            )

    @api.depends('replacement_car_qty')
    def _compute_replacement_ratio(self):
        for rec in self:
            # The percentage widget expects a ratio (e.g. 1/30), not a value
            # already multiplied by 100.
            rec.replacement_car_ratio = (
                1.0 / rec.replacement_car_qty
                if rec.replacement_car_qty else 0.0
            )

    @api.depends('jenis_transaksi_id', 'masa_sewa', 'masa_sewa_buffer')
    def _compute_umur_saat_dispose(self):
        for rec in self:
            if rec.jenis_transaksi_id and rec.jenis_transaksi_id.name == 'Regular-Used':
                rec.umur_saat_dispose = rec.masa_sewa + rec.masa_sewa_buffer + 1
            else:
                rec.umur_saat_dispose = rec.masa_sewa + 1

    @api.depends(
        'otr_final', 'resale_value_rate', 'umur_saat_dispose',
        'total_useful_life', 'jenis_transaksi_id', 'sisa_nilai_buku'
    )
    def _compute_resale(self):
        for rec in self:
            # The percentage widget stores 60% as 0.60.
            rec.resale_price = rec.otr_final * rec.resale_value_rate
            rec.total_accum_saat_dispose = rec.otr_final * (
                rec.umur_saat_dispose / rec.total_useful_life
            ) if rec.total_useful_life else 0.0

            if rec.jenis_transaksi_id and rec.jenis_transaksi_id.name == 'Regular-Used':
                rec.nilai_buku = rec.sisa_nilai_buku
            else:
                rec.nilai_buku = rec.otr_final - rec.total_accum_saat_dispose

    @api.depends('resale_price', 'nilai_buku')
    def _compute_catatan_rv(self):
        for rec in self:
            rec.estimasi_loss_nilai_buku = 0.0
            if rec.nilai_buku:
                selisih = rec.resale_price - rec.nilai_buku
                selisih_pct = (selisih / rec.nilai_buku) * 100.0

                if selisih > 0:
                    keterangan = 'di atas Nilai Buku'
                elif selisih < 0:
                    keterangan = 'di bawah Nilai Buku'
                    rec.estimasi_loss_nilai_buku = selisih
                else:
                    keterangan = 'sama dengan Nilai Buku'

                rec.catatan_rv = (
                    f"Selisih Resale Value dengan Nilai Buku: {selisih_pct:.1f}% "
                    f"{keterangan}"
                )
            else:
                rec.catatan_rv = ''

    # ─────────────────────────────────────────────
    # CONSTRAINTS
    # ─────────────────────────────────────────────

    @api.constrains('stnk_line_ids')
    def _check_stnk_max(self):
        for rec in self:
            if len(rec.stnk_line_ids) > 5:
                raise ValidationError(_('Estimasi Biaya STNK maksimal 5 baris!'))

    @api.constrains('service_line_ids')
    def _check_service_max(self):
        for rec in self:
            if len(rec.service_line_ids) > 5:
                raise ValidationError(_('Estimasi Biaya Service maksimal 5 baris!'))

    @api.constrains('hok', 'resale_value_pct', 'basis_otr')
    def _check_hok_fields(self):
        for rec in self:
            if rec.hok == 'yes' and not rec.resale_value_pct:
                raise ValidationError(_('Resale Value wajib diisi jika HOK = YES!'))
            if rec.hok == 'yes' and not rec.basis_otr:
                raise ValidationError(_('Basis OTR wajib diisi jika HOK = YES!'))
            if rec.hok == 'no' and (rec.resale_value_pct or rec.basis_otr):
                raise ValidationError(_('Resale Value dan Basis OTR harus kosong jika HOK = NO!'))

    # ─────────────────────────────────────────────
    # SEQUENCE / CRUD
    # ─────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('rpc.document') or 'New'
            if 'purchase_line_ids' not in vals:
                vals['purchase_line_ids'] = [
                    (0, 0, line_vals) for line_vals in self._default_purchase_line_values()
                ]
        return super().create(vals_list)

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'purchase_line_ids' in fields_list and not defaults.get('purchase_line_ids'):
            defaults['purchase_line_ids'] = [
                (0, 0, line_vals) for line_vals in self._default_purchase_line_values()
            ]
        return defaults

    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'name': 'New',
            'state': 'draft',
            'creation_date': fields.Date.today(),
        })
        return super().copy(default)

    # ─────────────────────────────────────────────
    # WORKFLOW ACTIONS
    # ─────────────────────────────────────────────

    def action_submit(self):
        """Marketing submit -> notifikasi Procurement & Operation"""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Hanya dokumen Draft yang bisa di-submit!'))
            rec._check_required_fields([
                'marketing_id', 'pembuat_rpc_id', 'partner_id', 'type_of_klien_id',
                'jenis_transaksi_id', 'tujuan_id', 'sumber_id', 'sumber_daya_id',
                'jenis_kendaraan_id', 'pemakaian_id',
                'merek_id', 'type_kendaraan', 'tahun_kendaraan', 'provinsi_id',
                'kota_id', 'hok', 'term_of_payment_due',
            ])
            rec._check_positive_fields([
                'masa_sewa', 'jumlah_unit', 'sewa_per_bulan_batas_atas',
                'sewa_per_bulan_batas_bawah', 'term_of_payment_hari',
            ])
            rec.state = 'submitted'
            rec.message_post(
                body=_('RPC %s telah di-submit oleh Marketing. '
                        'Silakan tim Procurement dan Operation mengisi data masing-masing.') % rec.name,
                subject=_('RPC Submitted: %s') % rec.name,
                subtype_xmlid='mail.mt_comment',
            )

    def action_procurement_submit(self):
        """Procurement submit bagiannya"""
        for rec in self:
            if rec.state not in ('submitted', 'operation_done'):
                raise UserError(_('Status harus Submitted atau Operation Done!'))
            if rec.purchase_line_ids:
                harga_otr_line = rec.purchase_line_ids.filtered(lambda line: line.line_type == 'harga_otr')[:1]
                if not harga_otr_line or harga_otr_line.amount <= 0:
                    raise UserError(_('Harga OTR harus lebih besar dari 0!'))
            else:
                rec._check_positive_fields(['harga_otr'])
            new_state = 'procurement_done' if rec.state == 'submitted' else 'finance_done'
            if rec.state == 'operation_done':
                new_state = 'finance_done'
            else:
                new_state = 'procurement_done'
            rec.state = new_state
            rec.message_post(
                body=_('Bagian Procurement telah diisi oleh %s.') % self.env.user.name
            )

    def action_operation_submit(self):
        """Operation submit bagiannya"""
        for rec in self:
            if rec.state not in ('submitted', 'procurement_done'):
                raise UserError(_('Status harus Submitted atau Procurement Done!'))
            rec._check_positive_fields([
                'biaya_towing', 'replacement_car_qty', 'resale_value_rate',
            ])
            if rec.jenis_transaksi_id.name == 'Regular-Used':
                rec._check_positive_fields(['sisa_nilai_buku'])
            new_state = 'operation_done' if rec.state == 'submitted' else 'finance_done'
            if rec.state == 'procurement_done':
                new_state = 'finance_done'
            else:
                new_state = 'operation_done'
            rec.state = new_state
            rec.message_post(
                body=_('Bagian Operation telah diisi oleh %s.') % self.env.user.name
            )

    def action_finance_submit(self):
        """Finance submit -> RPC Approved"""
        for rec in self:
            if rec.state != 'finance_done':
                raise UserError(_('Finance hanya bisa submit setelah Procurement dan Operation selesai!'))
            rec._check_required_fields(['leasing_bank_id', 'jenis_angsuran_id'])
            rec._check_positive_fields([
                'masa_kredit', 'down_payment_pct', 'bunga_pct', 'penalti_pct',
                'opex_pusat_pct', 'cost_of_fund_pct',
            ])
            rec.state = 'approved'
            rec.message_post(
                body=_('RPC %s telah disetujui dan selesai.') % rec.name
            )

    def action_cancel(self):
        """Cancel RPC (tidak dihapus, hanya ubah status)"""
        for rec in self:
            rec.state = 'cancelled'
            rec.message_post(body=_('RPC %s dibatalkan.') % rec.name)

    def action_reset_draft(self):
        for rec in self:
            rec.state = 'draft'
            rec.message_post(body=_('RPC %s dikembalikan ke Draft.') % rec.name)

# -*- coding: utf-8 -*-
from odoo import api, fields, models


FINANCE_TABLE_TYPE_SELECTION = [
    ('unit', 'PRE DAN POST DISBURMENT CASHFLOW TOTAL'),
    ('cashflow', 'PROYEKSI CASHFLOW BULANAN/UNIT'),
]

FINANCE_FORMULA_SELECTION = [
    ('total_downpayment_total', 'total_downpayment * jumlah_unit'),
    ('cashback_total', 'cashback * jumlah_unit'),
    (
        'insurance_year_1_total',
        'rate asuransi tahun 1 * otr_leasing * jumlah_unit',
    ),
    ('incentive_upper', 'insentif_jumlah_batas_atas'),
    ('incentive_lower', 'insentif_jumlah_batas_bawah'),
    ('net_cashflow_upper', 'T2 - T3 - T4 (Batas Atas)'),
    ('net_cashflow_lower', 'T2 - T3 - T4 (Batas Bawah)'),
    ('rent_upper', 'sewa_per_bulan_batas_atas'),
    ('rent_lower', 'sewa_per_bulan_batas_bawah'),
    (
        'cof_month_year_1',
        'Angsuran/Bulan + STNK Tahun 1/12 + Service Tahun 1/12',
    ),
    (
        'cof_month_year_2_onwards',
        'Angsuran/Bulan + STNK Tahun 2/12 + Service Tahun 2/12',
    ),
    ('ncf_month_year_1_upper', 'T1 Batas Atas - T2'),
    ('ncf_month_year_1_lower', 'T1 Batas Bawah - T2'),
    ('ncf_month_year_2_upper', 'T1 Batas Atas - T3'),
    ('ncf_month_year_2_lower', 'T1 Batas Bawah - T3'),
    (
        'gapping_month_year_1_upper',
        'TOTAL FUNDING Gapping Cost Batas Atas Tahun 1 / 12',
    ),
    (
        'gapping_month_year_1_lower',
        'TOTAL FUNDING Gapping Cost Batas Bawah Tahun 1 / 12',
    ),
    (
        'gapping_month_year_2_upper',
        'TOTAL FUNDING Gapping Cost Batas Atas '
        'Tahun 2-DST / (Masa Sewa - 12)',
    ),
    (
        'gapping_month_year_2_lower',
        'TOTAL FUNDING Gapping Cost Batas Bawah '
        'Tahun 2-DST / (Masa Sewa - 12)',
    ),
    (
        'rental_income_total_upper',
        '(T1 Batas Atas * Jumlah Unit) + Pendapatan Sewa/Bulan',
    ),
    (
        'rental_income_total_lower',
        '(T1 Batas Bawah * Jumlah Unit) + Pendapatan Sewa/Bulan',
    ),
]


class RpcDocumentInsuranceLine(models.Model):
    _name = 'rpc.document.insurance.line'
    _description = 'RPC Insurance Line'
    _order = 'document_id, sequence, tahun'

    document_id = fields.Many2one('rpc.document', string='RPC Document', required=True, ondelete='cascade')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='document_id.currency_id', store=True, readonly=True
    )
    sequence = fields.Integer(string='Sequence', default=10, readonly=True)
    tahun = fields.Integer(string='Tahun', readonly=True)
    asuransi_rate_id = fields.Many2one(
        'rpc.asuransi.rate',
        string='Asuransi Rate',
        ondelete='restrict',
        readonly=True,
    )
    rate = fields.Float(
        string='Rate (%)',
        readonly=True,
        digits=(5, 4),
    )
    amount = fields.Monetary(
        string='Amount',
        compute='_compute_amount',
        store=True,
        readonly=True,
        currency_field='currency_id',
    )

    @api.depends('rate', 'document_id.otr_final')
    def _compute_amount(self):
        for line in self:
            line.amount = line.rate * line.document_id.otr_final


class RpcFinanceLineType(models.Model):
    _name = 'rpc.finance.line.type'
    _description = 'RPC Finance Line Type Master'
    _order = 'table_type, sequence, id'

    name = fields.Char(string='Type', required=True)
    code = fields.Char(string='Kode', required=True)
    table_type = fields.Selection(
        FINANCE_TABLE_TYPE_SELECTION,
        string='Group',
        required=True,
        index=True,
    )
    formula_batas_atas = fields.Selection(
        FINANCE_FORMULA_SELECTION,
        string='Formula Batas Atas',
    )
    formula_batas_bawah = fields.Selection(
        FINANCE_FORMULA_SELECTION,
        string='Formula Batas Bawah',
    )
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    finance_line_ids = fields.One2many(
        'rpc.document.finance.line',
        'finance_type_id',
        string='Finance Lines',
    )

    _code_unique = models.Constraint(
        'UNIQUE(code)',
        'Kode Finance Line Type harus unik!',
    )
    _name_table_type_unique = models.Constraint(
        'UNIQUE(table_type, name)',
        'Nama Type harus unik pada setiap Group!',
    )


class RpcDocumentFinanceLine(models.Model):
    _name = 'rpc.document.finance.line'
    _description = 'RPC Finance Calculation Line'
    _order = 'document_id, table_type, sequence, id'

    document_id = fields.Many2one(
        'rpc.document',
        string='RPC Document',
        required=True,
        ondelete='cascade',
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='document_id.currency_id', store=True, readonly=True
    )
    finance_type_id = fields.Many2one(
        'rpc.finance.line.type',
        string='Type',
        required=True,
        ondelete='restrict',
        index=True,
        readonly=True,
    )
    table_type = fields.Selection(
        FINANCE_TABLE_TYPE_SELECTION,
        string='Group',
        related='finance_type_id.table_type',
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(
        string='Sequence',
        related='finance_type_id.sequence',
        store=True,
        readonly=True,
    )
    name = fields.Char(
        string='Type',
        related='finance_type_id.name',
        store=True,
        readonly=True,
    )
    batas_atas = fields.Monetary(
        string='Batas Atas',
        compute='_compute_amounts',
        store=True,
        readonly=True,
        currency_field='currency_id',
    )
    batas_bawah = fields.Monetary(
        string='Batas Bawah',
        compute='_compute_amounts',
        store=True,
        readonly=True,
        currency_field='currency_id',
    )

    _document_finance_type_unique = models.Constraint(
        'UNIQUE(document_id, finance_type_id)',
        'Type hanya boleh muncul satu kali pada setiap dokumen RPC!',
    )

    def _get_cashback_total(self):
        self.ensure_one()
        document = self.document_id
        cashback = document._get_effective_purchase_amount(
            'cashback', 'cashback'
        )
        return cashback * document.jumlah_unit

    def _get_insurance_year_1_total(self):
        self.ensure_one()
        document = self.document_id
        insurance_line = document.insurance_line_ids.sorted(
            lambda line: (line.tahun, line.sequence, line.id)
        )[:1]
        rate = insurance_line.rate if insurance_line else 0.0
        return rate * document.otr_leasing * document.jumlah_unit

    def _get_yearly_line_monthly_amount(self, lines, year_index):
        """Return one annual STNK/service amount converted to a monthly cost."""
        self.ensure_one()
        document = self.document_id
        ordered_lines = lines.sorted(
            lambda line: (line.tahun, line.sequence, line.id)
        )
        target_years = [year_index + 1]
        if document.tahun_mulai_sewa:
            target_years.insert(0, document.tahun_mulai_sewa + year_index)
        matching_line = ordered_lines.filtered(
            lambda line: line.tahun in target_years
        )[:1]
        if not matching_line and year_index < len(ordered_lines):
            matching_line = ordered_lines[year_index]
        return matching_line.amount / 12.0 if matching_line else 0.0

    def _get_cof_month(self, year_index):
        self.ensure_one()
        document = self.document_id
        return (
            document.angsuran_per_bulan
            + self._get_yearly_line_monthly_amount(
                document.stnk_line_ids, year_index
            )
            + self._get_yearly_line_monthly_amount(
                document.service_line_ids, year_index
            )
        )

    def _get_total_funding_year_amounts(self, limit_type):
        """Return Gapping TOTAL FUNDING values for years 1 through 5."""
        self.ensure_one()
        document = self.document_id
        lines = (
            document.gapping_cost_batas_atas_ids
            if limit_type == 'upper'
            else document.gapping_cost_batas_bawah_ids
        )
        total_funding_line = lines.filtered(
            lambda line: (
                (line.hierarchy_1_id.name or '').strip().casefold()
                == 'total funding'
                and not line.hierarchy_2_id
            )
        )[:1]
        if total_funding_line:
            return [
                total_funding_line[0][f'tahun_{year_number}']
                for year_number in range(1, 6)
            ]

        # Legacy fallback: sum detail rows only, excluding generated
        # Akumulasi/check rows which do not have Hierarchy 3.
        detail_lines = lines.filtered(lambda line: line.hierarchy_3_id)
        return [
            sum(detail_lines.mapped(f'tahun_{year_number}'))
            if detail_lines else 0.0
            for year_number in range(1, 6)
        ]

    def _get_total_funding_month(self, limit_type, year_index):
        """Return one Gapping TOTAL FUNDING year divided by 12 (Excel T6)."""
        year_amounts = self._get_total_funding_year_amounts(limit_type)
        return year_amounts[year_index] / 12.0

    def _get_total_funding_remaining_month(self, limit_type):
        """Return Excel T7: years 2-last total / remaining lease months."""
        self.ensure_one()
        lease_months = self.document_id.masa_sewa
        remaining_months = lease_months - 12
        if remaining_months <= 0:
            return 0.0
        year_amounts = self._get_total_funding_year_amounts(limit_type)
        lease_year_count = min(5, (lease_months + 11) // 12)
        return sum(year_amounts[1:lease_year_count]) / remaining_months

    def _get_rental_income_total(self, limit_type):
        self.ensure_one()
        document = self.document_id
        rent_per_unit = (
            document.sewa_per_bulan_batas_atas
            if limit_type == 'upper'
            else document.sewa_per_bulan_batas_bawah
        )
        return (
            rent_per_unit * document.jumlah_unit
            + document.pendapatan_sewa_per_bulan
        )

    def _evaluate_formula(self, formula):
        self.ensure_one()
        document = self.document_id
        if formula == 'total_downpayment_total':
            return document.total_downpayment * document.jumlah_unit
        if formula == 'cashback_total':
            return self._get_cashback_total()
        if formula == 'insurance_year_1_total':
            return self._get_insurance_year_1_total()
        if formula == 'incentive_upper':
            return document.insentif_jumlah_batas_atas
        if formula == 'incentive_lower':
            return document.insentif_jumlah_batas_bawah
        if formula == 'net_cashflow_upper':
            return (
                self._get_cashback_total()
                - self._get_insurance_year_1_total()
                - document.insentif_jumlah_batas_atas
            )
        if formula == 'net_cashflow_lower':
            return (
                self._get_cashback_total()
                - self._get_insurance_year_1_total()
                - document.insentif_jumlah_batas_bawah
            )
        if formula == 'rent_upper':
            return document.sewa_per_bulan_batas_atas
        if formula == 'rent_lower':
            return document.sewa_per_bulan_batas_bawah
        if formula == 'cof_month_year_1':
            return self._get_cof_month(0)
        if formula == 'cof_month_year_2_onwards':
            return self._get_cof_month(1)
        if formula == 'ncf_month_year_1_upper':
            return document.sewa_per_bulan_batas_atas - self._get_cof_month(0)
        if formula == 'ncf_month_year_1_lower':
            return document.sewa_per_bulan_batas_bawah - self._get_cof_month(0)
        if formula == 'ncf_month_year_2_upper':
            return document.sewa_per_bulan_batas_atas - self._get_cof_month(1)
        if formula == 'ncf_month_year_2_lower':
            return document.sewa_per_bulan_batas_bawah - self._get_cof_month(1)
        if formula == 'gapping_month_year_1_upper':
            return self._get_total_funding_month('upper', 0)
        if formula == 'gapping_month_year_1_lower':
            return self._get_total_funding_month('lower', 0)
        if formula == 'gapping_month_year_2_upper':
            return self._get_total_funding_remaining_month('upper')
        if formula == 'gapping_month_year_2_lower':
            return self._get_total_funding_remaining_month('lower')
        if formula == 'rental_income_total_upper':
            return self._get_rental_income_total('upper')
        if formula == 'rental_income_total_lower':
            return self._get_rental_income_total('lower')
        return 0.0

    @api.depends(
        'finance_type_id.formula_batas_atas',
        'finance_type_id.formula_batas_bawah',
        'document_id.total_downpayment',
        'document_id.jumlah_unit',
        'document_id.cashback',
        'document_id.otr_leasing',
        'document_id.angsuran_per_bulan',
        'document_id.tahun_mulai_sewa',
        'document_id.sewa_per_bulan_batas_atas',
        'document_id.sewa_per_bulan_batas_bawah',
        'document_id.pendapatan_sewa_per_bulan',
        'document_id.ruu_netto',
        'document_id.ruu_netto_batas_bawah',
        'document_id.otr_final',
        'document_id.masa_sewa',
        'document_id.sumber_id',
        'document_id.type_of_klien_id',
        'document_id.jenis_transaksi_id',
        'document_id.insentif_jumlah_batas_atas',
        'document_id.insentif_jumlah_batas_bawah',
        'document_id.purchase_line_ids.line_type',
        'document_id.purchase_line_ids.amount',
        'document_id.insurance_line_ids.tahun',
        'document_id.insurance_line_ids.sequence',
        'document_id.insurance_line_ids.rate',
        'document_id.stnk_line_ids.tahun',
        'document_id.stnk_line_ids.sequence',
        'document_id.stnk_line_ids.amount',
        'document_id.service_line_ids.tahun',
        'document_id.service_line_ids.sequence',
        'document_id.service_line_ids.amount',
        'document_id.gapping_cost_batas_atas_ids.tahun_1',
        'document_id.gapping_cost_batas_atas_ids.tahun_2',
        'document_id.gapping_cost_batas_atas_ids.tahun_3',
        'document_id.gapping_cost_batas_atas_ids.tahun_4',
        'document_id.gapping_cost_batas_atas_ids.tahun_5',
        'document_id.gapping_cost_batas_bawah_ids.tahun_1',
        'document_id.gapping_cost_batas_bawah_ids.tahun_2',
        'document_id.gapping_cost_batas_bawah_ids.tahun_3',
        'document_id.gapping_cost_batas_bawah_ids.tahun_4',
        'document_id.gapping_cost_batas_bawah_ids.tahun_5',
    )
    def _compute_amounts(self):
        for line in self:
            line.batas_atas = line._evaluate_formula(
                line.finance_type_id.formula_batas_atas
            )
            line.batas_bawah = line._evaluate_formula(
                line.finance_type_id.formula_batas_bawah
            )

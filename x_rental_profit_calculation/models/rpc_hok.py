# -*- coding: utf-8 -*-
import math

from odoo import api, fields, models
from odoo.tools.misc import format_amount, formatLang


HOK_COST_COMPONENTS = (
    ('interest', 'P4', 'Bunga Pembiayaan'),
    ('provision', 'P5', 'Provisi & Admin, Fidusia'),
    ('stnk', 'P6', 'STNK'),
    ('insurance', 'P7', 'Asuransi'),
    ('service', 'P8', 'Service'),
    ('towing', 'P9', 'Towing'),
    ('replacement', 'P10', 'Replacement Car'),
    ('features', 'P11', 'Fasilitas/Fitur Sewa'),
    ('opex', 'P12', 'Opex'),
    ('funding', 'P13', 'Funding'),
    ('penalty', 'P14', 'Penalti Pelunasan'),
    ('marketing', 'P15', 'Marketing & Komisi'),
    ('total', 'P16', 'Total Biaya'),
)

HOK_COST_SELECTION = [
    (key, f'{code} {name}') for key, code, name in HOK_COST_COMPONENTS
]

HOK_TENORS = (12, 24, 36, 48, 60)
HOK_RESALE_RATES = tuple(range(0, 81, 10))

HOK_COMPONENT_DEFINITIONS = (
    (
        'resale_amount', 'P3', 'Resale Value, Rp',
        'parameter', 'monetary', 10,
    ),
    ('interest', 'P4', 'Bunga Pembiayaan', 'cost', 'monetary', 10),
    ('provision', 'P5', 'Provisi & Admin, Fidusia', 'cost', 'monetary', 20),
    ('stnk', 'P6', 'STNK', 'cost', 'monetary', 30),
    ('insurance', 'P7', 'Asuransi', 'cost', 'monetary', 40),
    ('service', 'P8', 'Service', 'cost', 'monetary', 50),
    ('towing', 'P9', 'Towing', 'cost', 'monetary', 60),
    ('replacement', 'P10', 'Replacement Car', 'cost', 'monetary', 70),
    ('features', 'P11', 'Fasilitas/Fitur Sewa', 'cost', 'monetary', 80),
    ('opex', 'P12', 'Opex', 'cost', 'monetary', 90),
    ('funding', 'P13', 'Funding', 'cost', 'monetary', 100),
    ('penalty', 'P14', 'Penalti Pelunasan', 'cost', 'monetary', 110),
    ('marketing', 'P15', 'Marketing & Komisi', 'cost', 'monetary', 120),
    ('total', 'P16', 'Total Biaya', 'cost', 'monetary', 130),
    ('profit_base', 'P17/P24', 'Profit Base', 'result', 'percentage', 10),
    ('profit_amount', 'P18/P25', 'Profit, Rp', 'result', 'monetary', 20),
    ('rental_per_month', 'P19/P26', 'Rental/Bulan', 'result', 'monetary', 30),
    (
        'remaining_book_value', 'P20/P27', 'Sisa Nilai Buku',
        'result', 'monetary', 40,
    ),
    ('company_portion', 'P22/P29', 'Perusahaan', 'result', 'monetary', 50),
    (
        'hok_holder_portion', 'P23/P30', 'Pemegang HOK',
        'result', 'monetary', 60,
    ),
)

HOK_FORMULAS = {
    'resale_amount': 'Basis OTR x Resale Value %',
    'interest': 'Bunga x Pokok Hutang x Tenor/12',
    'provision': '(Provisi & Admin x Pokok Hutang) + Fidusia',
    'stnk': 'Funding Needs > Akumulasi/Unit > STNK pada tenor',
    'insurance': 'Funding Needs > Akumulasi/Unit > Asuransi pada tenor',
    'service': 'Funding Needs > Akumulasi/Unit > Service pada tenor',
    'towing': 'Biaya Towing x Tenor/12',
    'replacement': (
        'Funding Needs > Akumulasi/Unit > Replacement Car pada tenor'
    ),
    'features': 'Funding Needs > Akumulasi/Unit > Fitur Sewa pada tenor',
    'opex': (
        'Total Opex Funding / Masa Sewa x Tenor HOK / Jumlah Unit'
    ),
    'funding': (
        'Gapping Cost Batas Atas > Total Funding > Akumulasi / Jumlah Unit'
    ),
    'penalty': (
        'Jika Masa Kredit > Tenor: (Sisa Masa Kredit/Masa Kredit) '
        'x Pokok Hutang x Penalti'
    ),
    'marketing': (
        'Funding Needs > Akumulasi/Unit > Lumpsum/Unit Tahun 1 '
        '+ Bulanan pada tenor'
    ),
    'total': 'Jumlah seluruh komponen Cost Base',
    'profit_base': 'Profit RPC Batas Atas/Bawah dari tab RPC',
    'profit_amount': 'Profit Base x OTR Final',
    'rental_per_month': (
        '(Total Biaya + Sisa Nilai Buku + Profit - Resale Value) '
        'x (1 + Buffer) / Tenor'
    ),
    'remaining_book_value': '(96 - Tenor) x OTR Final / 96',
    'company_portion': 'Sewa per Bulan RPC Batas Atas (RPC!H33)',
    'hok_holder_portion': 'Rental/Bulan - Porsi Perusahaan',
}

# The same accumulated/annual column choice used when Logic Table is copied to
# Funding Needs and Gapping Cost. This keeps HOK and those four tables aligned.
HOK_ACCUMULATED_CODES = frozenset({
    'BVK01', 'BVK02', 'BVK03', 'FT01', 'FT02', 'FT04',
})


class RpcHokComponent(models.Model):
    _name = 'rpc.hok.component'
    _description = 'Master Komponen HOK'
    _order = 'category, sequence, id'

    name = fields.Char(string='Nama Komponen', required=True, translate=True)
    code = fields.Char(string='Kode Rumus', required=True, index=True, copy=False)
    excel_code = fields.Char(string='Referensi Excel', readonly=True)
    category = fields.Selection([
        ('parameter', 'Parameter'),
        ('cost', 'Cost Base'),
        ('result', 'Hasil Perhitungan'),
    ], string='Kategori', required=True, readonly=True)
    value_format = fields.Selection([
        ('monetary', 'Nominal'),
        ('percentage', 'Persentase'),
    ], string='Format Nilai', required=True, readonly=True)
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        'UNIQUE(code)',
        'Kode rumus komponen HOK harus unik!',
    )


class RpcDocumentHokMatrixLine(models.Model):
    _name = 'rpc.document.hok.matrix.line'
    _description = 'RPC HOK Tenor and Resale Value Matrix'
    _order = 'document_id, tenor_months, sequence, id'

    document_id = fields.Many2one(
        'rpc.document', required=True, ondelete='cascade', index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='document_id.currency_id',
        store=True, readonly=True,
    )
    tenor_months = fields.Integer(string='Tenor', required=True, readonly=True)
    sequence = fields.Integer(readonly=True)
    section = fields.Selection([
        ('parameter', 'Resale Value'),
        ('cost', 'Cost Base'),
        ('upper', 'Batas Atas'),
        ('lower', 'Batas Bawah'),
    ], string='Bagian', required=True, readonly=True)
    component_id = fields.Many2one(
        'rpc.hok.component', string='Komponen', required=True,
        readonly=True, ondelete='restrict',
    )
    component_code = fields.Char(
        related='component_id.code', store=True, readonly=True,
    )
    formula = fields.Char(string='Formula', readonly=True)

    value_0 = fields.Float(digits=(20, 12), readonly=True)
    value_10 = fields.Float(digits=(20, 12), readonly=True)
    value_20 = fields.Float(digits=(20, 12), readonly=True)
    value_30 = fields.Float(digits=(20, 12), readonly=True)
    value_40 = fields.Float(digits=(20, 12), readonly=True)
    value_50 = fields.Float(digits=(20, 12), readonly=True)
    value_60 = fields.Float(digits=(20, 12), readonly=True)
    value_70 = fields.Float(digits=(20, 12), readonly=True)
    value_80 = fields.Float(digits=(20, 12), readonly=True)

    display_0 = fields.Char(string='0%', compute='_compute_display_values')
    display_10 = fields.Char(string='10%', compute='_compute_display_values')
    display_20 = fields.Char(string='20%', compute='_compute_display_values')
    display_30 = fields.Char(string='30%', compute='_compute_display_values')
    display_40 = fields.Char(string='40%', compute='_compute_display_values')
    display_50 = fields.Char(string='50%', compute='_compute_display_values')
    display_60 = fields.Char(string='60%', compute='_compute_display_values')
    display_70 = fields.Char(string='70%', compute='_compute_display_values')
    display_80 = fields.Char(string='80%', compute='_compute_display_values')

    _document_tenor_section_component_unique = models.Constraint(
        'UNIQUE(document_id, tenor_months, section, component_id)',
        'Komponen hanya boleh muncul satu kali pada setiap tabel tenor HOK!',
    )

    @api.depends(
        'component_id.value_format', 'currency_id',
        'value_0', 'value_10', 'value_20', 'value_30', 'value_40',
        'value_50', 'value_60', 'value_70', 'value_80',
    )
    def _compute_display_values(self):
        for line in self:
            for rate in HOK_RESALE_RATES:
                value = line[f'value_{rate}']
                if line.component_id.value_format == 'percentage':
                    display = '%s%%' % formatLang(
                        line.env, value * 100.0, digits=2,
                    )
                elif line.currency_id:
                    display = format_amount(
                        line.env, value, line.currency_id,
                    )
                else:
                    display = formatLang(line.env, value, digits=2)
                line[f'display_{rate}'] = display


class RpcDocumentHokCostLine(models.Model):
    _name = 'rpc.document.hok.cost.line'
    _description = 'RPC HOK Cost Base Line'
    _order = 'document_id, sequence, id'

    document_id = fields.Many2one(
        'rpc.document', required=True, ondelete='cascade', index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='document_id.currency_id',
        store=True, readonly=True,
    )
    sequence = fields.Integer(readonly=True)
    component = fields.Selection(
        HOK_COST_SELECTION, string='Komponen', required=True, readonly=True,
    )
    formula = fields.Char(string='Formula', readonly=True)
    batas_atas = fields.Monetary(
        string='Batas Atas', currency_field='currency_id', readonly=True,
    )
    batas_bawah = fields.Monetary(
        string='Batas Bawah', currency_field='currency_id', readonly=True,
    )

    _document_component_unique = models.Constraint(
        'UNIQUE(document_id, component)',
        'Komponen HOK hanya boleh muncul satu kali pada setiap dokumen RPC!',
    )


class RpcDocumentHokResultLine(models.Model):
    _name = 'rpc.document.hok.result.line'
    _description = 'RPC HOK Result Line'
    _order = 'document_id, sequence, id'

    document_id = fields.Many2one(
        'rpc.document', required=True, ondelete='cascade', index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='document_id.currency_id',
        store=True, readonly=True,
    )
    sequence = fields.Integer(readonly=True)
    limit_type = fields.Selection([
        ('batas_atas', 'Batas Atas'),
        ('batas_bawah', 'Batas Bawah'),
    ], string='Perhitungan', required=True, readonly=True)
    profit_base = fields.Float(
        string='Profit Base', digits=(16, 12), readonly=True,
    )
    profit_amount = fields.Monetary(
        string='Profit', currency_field='currency_id', readonly=True,
    )
    rental_per_month = fields.Monetary(
        string='Rental/Bulan', currency_field='currency_id', readonly=True,
    )
    remaining_book_value = fields.Monetary(
        string='Sisa Nilai Buku', currency_field='currency_id', readonly=True,
    )
    company_portion = fields.Monetary(
        string='Perusahaan', currency_field='currency_id', readonly=True,
    )
    hok_holder_portion = fields.Monetary(
        string='Pemegang HOK', currency_field='currency_id', readonly=True,
    )

    _document_limit_unique = models.Constraint(
        'UNIQUE(document_id, limit_type)',
        'Hasil Batas HOK hanya boleh muncul satu kali pada setiap dokumen RPC!',
    )


class RpcDocument(models.Model):
    _inherit = 'rpc.document'

    hok_matrix_line_ids = fields.One2many(
        'rpc.document.hok.matrix.line', 'document_id',
        string='Matriks HOK', copy=False,
    )
    hok_tenor_12_line_ids = fields.One2many(
        'rpc.document.hok.matrix.line', 'document_id',
        string='HOK Tenor 12 Bulan', copy=False,
        domain=[('tenor_months', '=', 12)],
    )
    hok_tenor_24_line_ids = fields.One2many(
        'rpc.document.hok.matrix.line', 'document_id',
        string='HOK Tenor 24 Bulan', copy=False,
        domain=[('tenor_months', '=', 24)],
    )
    hok_tenor_36_line_ids = fields.One2many(
        'rpc.document.hok.matrix.line', 'document_id',
        string='HOK Tenor 36 Bulan', copy=False,
        domain=[('tenor_months', '=', 36)],
    )
    hok_tenor_48_line_ids = fields.One2many(
        'rpc.document.hok.matrix.line', 'document_id',
        string='HOK Tenor 48 Bulan', copy=False,
        domain=[('tenor_months', '=', 48)],
    )
    hok_tenor_60_line_ids = fields.One2many(
        'rpc.document.hok.matrix.line', 'document_id',
        string='HOK Tenor 60 Bulan', copy=False,
        domain=[('tenor_months', '=', 60)],
    )
    hok_cost_line_ids = fields.One2many(
        'rpc.document.hok.cost.line', 'document_id',
        string='Cost Base HOK', copy=False,
    )
    hok_result_line_ids = fields.One2many(
        'rpc.document.hok.result.line', 'document_id',
        string='Hasil Perhitungan HOK', copy=False,
    )
    hok_basis_otr_amount = fields.Monetary(
        string='Nilai Basis OTR', currency_field='currency_id',
        compute='_compute_hok_parameter_amounts',
    )
    hok_resale_value_amount = fields.Monetary(
        string='Resale Value', currency_field='currency_id',
        compute='_compute_hok_parameter_amounts',
    )

    _HOK_SOURCE_FIELDS = frozenset({
        'state', 'hok', 'basis_otr', 'resale_value_pct', 'buffer_hok',
        'masa_sewa', 'jumlah_unit', 'harga_otr', 'discount', 'cashback',
        'biaya_ekspedisi', 'purchase_line_ids',
        'special_req_1_amount', 'special_req_2_amount',
        'special_req_3_amount', 'special_req_4_amount',
        'special_req_5_amount',
        'masa_kredit', 'bunga_pct', 'pokok_hutang',
        'provisi_admin_pct', 'fidusia', 'penalti_pct', 'opex_pusat_pct',
        'biaya_towing', 'replacement_car_qty', 'stnk_line_ids',
        'service_line_ids', 'insurance_line_ids',
        'management_fee', 'free_own_risk', 'bank_garansi_deposit',
        'asuransi_jiwa_pa', 'pic_internal', 'infrastruktur',
        'komisi_proyek', 'lainnya_marketing', 'cost_of_fund_pct',
        'resale_value_rate', 'sisa_nilai_buku',
        'total_useful_life', 'masa_sewa_buffer', 'jenis_transaksi_id',
        'sewa_per_bulan_batas_atas', 'sewa_per_bulan_batas_bawah',
    })

    def _get_hok_basis_otr(self):
        """Return O1 from the HOK sheet using the selected OTR basis."""
        self.ensure_one()
        if self.basis_otr != 'gross_otr':
            return self.otr_final

        harga_otr = self._get_effective_purchase_amount(
            'harga_otr', 'harga_otr'
        )
        special_request_lines = self.purchase_line_ids.filtered(
            lambda line: line.line_type
            and line.line_type.startswith('special_req_')
        )
        if special_request_lines:
            special_request_total = sum(special_request_lines.mapped('amount'))
        else:
            special_request_total = sum((
                self.special_req_1_amount,
                self.special_req_2_amount,
                self.special_req_3_amount,
                self.special_req_4_amount,
                self.special_req_5_amount,
            ))
        # HOK!F5: Gross OTR is the vehicle price plus Special Request only.
        # Shipping remains part of Net OTR (the canonical OTR Final field).
        return harga_otr + special_request_total

    @api.depends(
        'basis_otr', 'resale_value_pct', 'otr_final', 'harga_otr',
        'biaya_ekspedisi', 'purchase_line_ids.amount',
        'purchase_line_ids.line_type', 'special_req_1_amount',
        'special_req_2_amount', 'special_req_3_amount',
        'special_req_4_amount', 'special_req_5_amount',
    )
    def _compute_hok_parameter_amounts(self):
        for document in self:
            basis_otr = document._get_hok_basis_otr()
            document.hok_basis_otr_amount = basis_otr
            document.hok_resale_value_amount = (
                basis_otr * document.resale_value_pct
            )

    def _hok_logic_values(self, year_count, limit_type):
        """Return the selected-year Funding/Gapping values per cost code."""
        self.ensure_one()
        limit_suffix = (
            'batas_atas' if limit_type == 'batas_atas' else 'batas_bawah'
        )
        lines_by_code = {}
        for line in self.logic_table_ids:
            code = (line.variable or '').strip().upper()
            if code and line.year_index <= year_count:
                lines_by_code.setdefault(code, []).append(line)

        funding_values = {}
        gapping_values = {}
        for code, lines in lines_by_code.items():
            selected_line = max(lines, key=lambda line: (
                line.year_index, line.sequence, line.id
            ))
            if code in HOK_ACCUMULATED_CODES:
                funding_field = f'akumulasi_total_{limit_suffix}'
                gapping_field = (
                    f'akumulasi_gapping_total_{limit_suffix}'
                )
            else:
                funding_field = f'total_year_{limit_suffix}'
                gapping_field = f'gapping_total_year_{limit_suffix}'
            funding_values[code] = selected_line[funding_field]
            gapping_values[code] = selected_line[gapping_field]
        return funding_values, gapping_values

    def _hok_summary_amount(
        self, line_field, hierarchy_1, hierarchy_2, year_count,
    ):
        """Read the exact aggregate row referenced by the HOK XLSX."""
        self.ensure_one()
        hierarchy_1 = hierarchy_1.strip().casefold()
        hierarchy_2 = hierarchy_2.strip().casefold()
        lines = self[line_field].filtered(
            lambda line: (
                (line.hierarchy_1_id.name or '').strip().casefold()
                == hierarchy_1
                and (line.hierarchy_2_id.name or '').strip().casefold()
                == hierarchy_2
            )
        )
        if not lines:
            return None
        year_count = min(max(int(year_count), 1), 5)
        return lines[:1][f'tahun_{year_count}']

    def _hok_cost_values(self, tenor):
        """Compute the HOK Cost Base for one of the five Excel tenors."""
        self.ensure_one()
        year_count = min(max(math.ceil(tenor / 12.0), 1), 5)
        qty = self.jumlah_unit or 1
        contract_active = self.masa_sewa >= tenor
        funding_values, gapping_values = self._hok_logic_values(
            year_count, 'batas_atas'
        )

        def funding_summary(name, fallback_code=None):
            amount = self._hok_summary_amount(
                'funding_needs_batas_atas_ids',
                'AKUMULASI/UNIT', name, year_count,
            )
            if amount is not None:
                return amount
            if fallback_code:
                return funding_values.get(fallback_code, 0.0) / qty
            return 0.0

        interest = 0.0
        if contract_active and self.masa_kredit > 0:
            interest = self.bunga_pct * self.pokok_hutang * tenor / 12.0
        provision = (
            self.provisi_admin_pct * self.pokok_hutang + self.fidusia
            if contract_active else 0.0
        )

        stnk = funding_summary('STNK', 'BVK01')
        insurance = funding_summary('ASURANSI', 'BVK02')
        service = funding_summary('SERVICE', 'BVK03')
        replacement = funding_summary('REPLACEMENT CAR', 'BVK04')
        features = funding_summary('FITUR SEWA')
        if not features:
            feature_codes = ('FT01', 'FT02', 'FT03', 'FT04')
            features = sum(
                funding_values.get(code, 0.0) for code in feature_codes
            ) / qty

        towing = self.biaya_towing * tenor / 12.0 if contract_active else 0.0
        lease_year_count = min(
            max(math.ceil(self.masa_sewa / 12.0), 1), 5
        )
        total_opex_funding = self._hok_summary_amount(
            'funding_needs_batas_atas_ids',
            'OPEX', 'OPX01', lease_year_count,
        )
        if total_opex_funding is None:
            full_term_funding_values, _gapping_values = (
                self._hok_logic_values(lease_year_count, 'batas_atas')
            )
            total_opex_funding = full_term_funding_values.get('OPX01', 0.0)
        opex = (
            total_opex_funding / self.masa_sewa * tenor / qty
            if contract_active and self.masa_sewa > 0 else 0.0
        )

        funding = self._hok_summary_amount(
            'gapping_cost_batas_atas_ids',
            'TOTAL FUNDING', 'Akumulasi', year_count,
        )
        if funding is None:
            funding = sum(gapping_values.values())
        funding /= qty

        penalty = (
            ((self.masa_kredit - tenor) / self.masa_kredit)
            * self.pokok_hutang * self.penalti_pct
            if self.masa_kredit > tenor and self.masa_kredit > 0 else 0.0
        )

        marketing_lumpsum = self._hok_summary_amount(
            'funding_needs_batas_atas_ids',
            'AKUMULASI/UNIT', 'Lumpsum/unit', 1,
        )
        marketing_monthly = self._hok_summary_amount(
            'funding_needs_batas_atas_ids',
            'AKUMULASI/UNIT', 'Bulanan', year_count,
        )
        if marketing_lumpsum is None or marketing_monthly is None:
            marketing_codes = ('MK01', 'MK02', 'MK03', 'MK04')
            marketing = sum(
                funding_values.get(code, 0.0) for code in marketing_codes
            ) / qty
        else:
            marketing = marketing_lumpsum + marketing_monthly

        values = {
            'interest': interest,
            'provision': provision,
            'stnk': stnk,
            'insurance': insurance,
            'service': service,
            'towing': towing,
            'replacement': replacement,
            'features': features,
            'opex': opex,
            'funding': funding,
            'penalty': penalty,
            'marketing': marketing,
        }
        values['total'] = sum(values.values())
        return values

    def _hok_profit_bases(self):
        """Return the RPC full-tenor profit ratios used by every HOK table."""
        self.ensure_one()
        profitability = {
            line['component']: line
            for line in self._rpc_profitability_values()
        }
        profit = profitability['profit_per_unit']
        denominator = self.otr_final
        return {
            'batas_atas': (
                profit['batas_atas'] / denominator if denominator else 0.0
            ),
            'batas_bawah': (
                profit['batas_bawah'] / denominator if denominator else 0.0
            ),
        }

    def _hok_scenario_values(
        self, tenor, resale_rate, limit_type, costs=None, profit_bases=None,
    ):
        """Compute one tenor/resale scenario using the HOK sheet formulas."""
        self.ensure_one()
        costs = costs or self._hok_cost_values(tenor)
        profit_bases = profit_bases or self._hok_profit_bases()
        contract_active = self.masa_sewa >= tenor
        if not contract_active or tenor <= 0:
            return {
                'costs': costs,
                'resale_amount': 0.0,
                'profit_base': 0.0,
                'profit_amount': 0.0,
                'rental_per_month': 0.0,
                'remaining_book_value': 0.0,
                'company_portion': 0.0,
                'hok_holder_portion': 0.0,
            }

        profit_base = profit_bases[limit_type]
        profit_amount = profit_base * self.otr_final
        resale_amount = self._get_hok_basis_otr() * resale_rate
        remaining_book_value = (
            (96.0 - tenor) * self.otr_final / 96.0
        )
        rental_per_month = (
            (
                costs['total'] + remaining_book_value + profit_amount
                - resale_amount
            )
            * (1.0 + self.buffer_hok)
            / tenor
        )
        # Every Perusahaan row in all five Excel blocks points to RPC!H33,
        # including the Batas Bawah section.
        company_portion = self.sewa_per_bulan_batas_atas
        return {
            'costs': costs,
            'resale_amount': resale_amount,
            'profit_base': profit_base,
            'profit_amount': profit_amount,
            'rental_per_month': rental_per_month,
            'remaining_book_value': remaining_book_value,
            'company_portion': company_portion,
            'hok_holder_portion': rental_per_month - company_portion,
        }

    def _hok_calculation_values(self):
        """Compute the selected tenor/resale scenario shown on the RPC tab."""
        self.ensure_one()
        costs = self._hok_cost_values(self.masa_sewa)
        profit_bases = self._hok_profit_bases()
        return {
            limit_type: self._hok_scenario_values(
                self.masa_sewa,
                self.resale_value_pct,
                limit_type,
                costs=costs,
                profit_bases=profit_bases,
            )
            for limit_type in ('batas_atas', 'batas_bawah')
        }

    def _ensure_hok_components(self):
        """Return all formula components without overwriting user-made names."""
        component_model = self.env['rpc.hok.component'].sudo().with_context(
            active_test=False,
        )
        components = {
            component.code: component
            for component in component_model.search([])
        }
        for code, excel_code, name, category, value_format, sequence in (
            HOK_COMPONENT_DEFINITIONS
        ):
            if code not in components:
                components[code] = component_model.create({
                    'name': name,
                    'code': code,
                    'excel_code': excel_code,
                    'category': category,
                    'value_format': value_format,
                    'sequence': sequence,
                })
        return components

    def _generate_hok_lines(self):
        matrix_model = self.env['rpc.document.hok.matrix.line']
        old_cost_model = self.env['rpc.document.hok.cost.line']
        old_result_model = self.env['rpc.document.hok.result.line']
        components = self._ensure_hok_components()
        cost_definitions = [
            definition for definition in HOK_COMPONENT_DEFINITIONS
            if definition[3] == 'cost'
        ]
        result_definitions = [
            definition for definition in HOK_COMPONENT_DEFINITIONS
            if definition[3] == 'result'
        ]
        parameter_definitions = [
            definition for definition in HOK_COMPONENT_DEFINITIONS
            if definition[3] == 'parameter'
        ]

        for document in self:
            matrix_model.search([('document_id', '=', document.id)]).unlink()
            old_cost_model.search([('document_id', '=', document.id)]).unlink()
            old_result_model.search([('document_id', '=', document.id)]).unlink()
            if (
                document.hok != 'yes'
                or document.tahun_mulai_sewa <= 0
                or document.masa_sewa <= 0
                or document.otr_final <= 0
            ):
                continue

            profit_bases = document._hok_profit_bases()
            line_values = []
            for tenor in HOK_TENORS:
                costs = document._hok_cost_values(tenor)
                scenarios = {
                    rate: {
                        limit_type: document._hok_scenario_values(
                            tenor,
                            rate / 100.0,
                            limit_type,
                            costs=costs,
                            profit_bases=profit_bases,
                        )
                        for limit_type in ('batas_atas', 'batas_bawah')
                    }
                    for rate in HOK_RESALE_RATES
                }

                for code, _excel, _name, _category, _format, sequence in (
                    parameter_definitions
                ):
                    line_values.append({
                        'document_id': document.id,
                        'tenor_months': tenor,
                        'sequence': 100 + sequence,
                        'section': 'parameter',
                        'component_id': components[code].id,
                        'formula': HOK_FORMULAS[code],
                        **{
                            f'value_{rate}': (
                                scenarios[rate]['batas_atas'][code]
                            )
                            for rate in HOK_RESALE_RATES
                        },
                    })

                for code, _excel, _name, _category, _format, sequence in (
                    cost_definitions
                ):
                    line_values.append({
                        'document_id': document.id,
                        'tenor_months': tenor,
                        'sequence': 1000 + sequence,
                        'section': 'cost',
                        'component_id': components[code].id,
                        'formula': HOK_FORMULAS[code],
                        **{
                            f'value_{rate}': costs[code]
                            for rate in HOK_RESALE_RATES
                        },
                    })

                for limit_type, section, section_sequence in (
                    ('batas_atas', 'upper', 2000),
                    ('batas_bawah', 'lower', 3000),
                ):
                    for code, _excel, _name, _category, _format, sequence in (
                        result_definitions
                    ):
                        line_values.append({
                            'document_id': document.id,
                            'tenor_months': tenor,
                            'sequence': section_sequence + sequence,
                            'section': section,
                            'component_id': components[code].id,
                            'formula': HOK_FORMULAS[code],
                            **{
                                f'value_{rate}': (
                                    scenarios[rate][limit_type][code]
                                )
                                for rate in HOK_RESALE_RATES
                            },
                        })
            matrix_model.create(line_values)

    def write(self, vals):
        result = super().write(vals)
        if self._HOK_SOURCE_FIELDS.intersection(vals):
            for document in self:
                if document.state in ('finance_done', 'approved'):
                    document._generate_hok_lines()
                elif vals.get('state') in ('draft', 'cancelled'):
                    document.hok_matrix_line_ids.unlink()
                    document.hok_cost_line_ids.unlink()
                    document.hok_result_line_ids.unlink()
        return result

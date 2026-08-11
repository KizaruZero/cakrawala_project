# -*- coding: utf-8 -*-
import math

from odoo import api, fields, models


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

# The same accumulated/annual column choice used when Logic Table is copied to
# Funding Needs and Gapping Cost. This keeps HOK and those four tables aligned.
HOK_ACCUMULATED_CODES = frozenset({
    'BVK01', 'BVK02', 'BVK03', 'FT01', 'FT02', 'FT04',
})


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
        biaya_ekspedisi = self._get_effective_purchase_amount(
            'biaya_ekspedisi', 'biaya_ekspedisi'
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
        # Gross OTR in the XLSX is price plus additions, before discount and
        # cashback. Net OTR uses the canonical OTR Final field.
        return harga_otr + special_request_total + biaya_ekspedisi

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

    def _hok_cost_values(self, limit_type):
        """Compute P4-P15 for the selected document tenor, per unit."""
        self.ensure_one()
        tenor = self.masa_sewa
        year_count = math.ceil(tenor / 12.0) if tenor > 0 else 0
        qty = self.jumlah_unit or 1
        funding_values, gapping_values = self._hok_logic_values(
            year_count, limit_type
        )

        interest = 0.0
        if self.masa_kredit > 0 and tenor > 0:
            interest = (
                (self.masa_kredit / 12.0)
                * self.bunga_pct
                * self.pokok_hutang
                * (tenor / self.masa_kredit)
            )
        provision = self.provisi_admin_pct * self.pokok_hutang + self.fidusia

        stnk = funding_values.get('BVK01', 0.0) / qty
        insurance = funding_values.get('BVK02', 0.0) / qty
        service = funding_values.get('BVK03', 0.0) / qty
        replacement = funding_values.get('BVK04', 0.0) / qty

        # Fallbacks make the tab useful before an old document has had its
        # Logic Table regenerated.
        if not stnk:
            stnk = sum(
                self.stnk_line_ids.sorted(
                    key=lambda line: (line.sequence, line.tahun, line.id)
                )[:year_count].mapped('amount')
            )
        if not insurance:
            insurance = sum(
                self.insurance_line_ids.sorted(
                    key=lambda line: (line.sequence, line.tahun, line.id)
                )[:year_count].mapped('amount')
            )
        if not service:
            service = sum(
                self.service_line_ids.sorted(
                    key=lambda line: (line.sequence, line.tahun, line.id)
                )[:year_count].mapped('amount')
            )
        if not replacement and year_count:
            year = self.tahun_mulai_sewa + year_count - 1
            replacement = self._logic_table_amounts(
                'BVK04', year, year_count - 1, year_count
            )[2] / qty

        towing = self.biaya_towing * year_count
        feature_codes = ('FT01', 'FT02', 'FT03', 'FT04')
        features = sum(funding_values.get(code, 0.0) for code in feature_codes)
        features /= qty
        if not features:
            features = (
                (self.management_fee + self.free_own_risk
                 + self.asuransi_jiwa_pa) * year_count
                + self.bank_garansi_deposit
            )

        opex = self.otr_final * self.opex_pusat_pct * tenor / 12.0
        funding = sum(gapping_values.values()) / qty
        penalty = (
            ((self.masa_kredit - tenor) / self.masa_kredit)
            * self.penalti_pct
            * self.pokok_hutang
            if self.masa_kredit > tenor and self.masa_kredit > 0 else 0.0
        )
        marketing_codes = ('MK01', 'MK02', 'MK03', 'MK04')
        marketing = sum(
            funding_values.get(code, 0.0) for code in marketing_codes
        ) / qty
        if not marketing:
            marketing = self.total_biaya_marketing / qty

        return {
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

    def _hok_calculation_values(self):
        """Compute the P1-P30 HOK specification for both RPC limits."""
        self.ensure_one()
        tenor = self.masa_sewa
        basis_otr = self._get_hok_basis_otr()
        resale_amount = basis_otr * self.resale_value_pct
        remaining_book_value = (
            self.otr_final * ((96.0 - tenor) / 96.0)
            - (self.resale_value_pct * self.otr_final)
            if tenor else 0.0
        )
        calculations = {}
        for limit_type, rent in (
            ('batas_atas', self.sewa_per_bulan_batas_atas),
            ('batas_bawah', self.sewa_per_bulan_batas_bawah),
        ):
            costs = self._hok_cost_values(limit_type)
            total_cost = sum(costs.values())

            # Z18 from the RPC specification: total income minus total cost and
            # the standard book value, expressed as a ratio of OTR Final.
            standard_income = rent * tenor + self.resale_price
            standard_profit = standard_income - total_cost - self.nilai_buku
            profit_base = (
                standard_profit / self.otr_final if self.otr_final else 0.0
            )
            profit_amount = profit_base * self.otr_final
            rental_per_month = (
                (
                    total_cost + profit_amount + remaining_book_value
                    - resale_amount
                )
                * (1.0 + self.buffer_hok)
                / tenor
                if tenor else 0.0
            )
            calculations[limit_type] = {
                'costs': {**costs, 'total': total_cost},
                'profit_base': profit_base,
                'profit_amount': profit_amount,
                'rental_per_month': rental_per_month,
                'remaining_book_value': remaining_book_value,
                'company_portion': rent,
                'hok_holder_portion': rental_per_month - rent,
            }
        return calculations

    def _generate_hok_lines(self):
        cost_model = self.env['rpc.document.hok.cost.line']
        result_model = self.env['rpc.document.hok.result.line']
        formulas = {
            'interest': '(Masa Kredit/12) × Bunga × Pokok Hutang × (Tenor/Masa Kredit)',
            'provision': '(Provisi & Admin × Pokok Hutang) + Fidusia',
            'stnk': 'Akumulasi STNK sampai tahun tenor / Jumlah Unit',
            'insurance': 'Akumulasi Asuransi sampai tahun tenor / Jumlah Unit',
            'service': 'Akumulasi Service sampai tahun tenor / Jumlah Unit',
            'towing': 'Biaya Towing × jumlah tahun tenor',
            'replacement': 'Replacement Car tahun tenor dari Logic Table / Jumlah Unit',
            'features': 'Total Fasilitas/Fitur tahun tenor / Jumlah Unit',
            'opex': 'OTR Final × Opex Pusat × Tenor/12',
            'funding': 'Akumulasi Gapping Cost tahun tenor / Jumlah Unit',
            'penalty': 'Sisa tenor kredit × Penalti × Pokok Hutang',
            'marketing': 'Total Marketing & Komisi tahun tenor / Jumlah Unit',
            'total': 'Jumlah P4 sampai P15',
        }
        for document in self:
            cost_model.search([('document_id', '=', document.id)]).unlink()
            result_model.search([('document_id', '=', document.id)]).unlink()
            if (
                document.hok != 'yes'
                or document.tahun_mulai_sewa <= 0
                or document.masa_sewa <= 0
                or document.otr_final <= 0
            ):
                continue

            calculations = document._hok_calculation_values()
            cost_model.create([
                {
                    'document_id': document.id,
                    'sequence': sequence * 10,
                    'component': component,
                    'formula': formulas[component],
                    'batas_atas': calculations['batas_atas']['costs'][component],
                    'batas_bawah': calculations['batas_bawah']['costs'][component],
                }
                for sequence, (component, _code, _name)
                in enumerate(HOK_COST_COMPONENTS, start=1)
            ])
            result_model.create([
                {
                    'document_id': document.id,
                    'sequence': sequence * 10,
                    'limit_type': limit_type,
                    **{
                        field_name: calculations[limit_type][field_name]
                        for field_name in (
                            'profit_base', 'profit_amount',
                            'rental_per_month', 'remaining_book_value',
                            'company_portion', 'hok_holder_portion',
                        )
                    },
                }
                for sequence, limit_type in enumerate(
                    ('batas_atas', 'batas_bawah'), start=1
                )
            ])

    def write(self, vals):
        result = super().write(vals)
        if self._HOK_SOURCE_FIELDS.intersection(vals):
            for document in self:
                if document.state in ('finance_done', 'approved'):
                    document._generate_hok_lines()
                elif vals.get('state') in ('draft', 'cancelled'):
                    document.hok_cost_line_ids.unlink()
                    document.hok_result_line_ids.unlink()
        return result

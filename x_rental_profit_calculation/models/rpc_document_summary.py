# -*- coding: utf-8 -*-
import math

from odoo import api, fields, models


RPC_PROFITABILITY_COMPONENTS = [
    ('rental_income', 'Pendapatan Sewa'),
    ('disposal_resale', 'Disposal/Resale'),
    ('total_income', 'Total Pendapatan'),
    ('interest', 'Bunga Pembiayaan'),
    ('provision', 'Provisi & Admin, Fidusia'),
    ('stnk', 'STNK'),
    ('insurance', 'Asuransi'),
    ('service', 'Service'),
    ('towing', 'Towing'),
    ('replacement', 'Replacement Car'),
    ('features', 'Fasilitas/Fitur Sewa'),
    ('opex', 'Opex'),
    ('funding', 'Funding'),
    ('penalty', 'Penalti Pelunasan'),
    ('marketing', 'Marketing & Komisi'),
    ('total_cost', 'Total Biaya'),
    ('remaining_book_value', 'Sisa Nilai Buku'),
    ('profit_per_unit', 'Profit Per Unit'),
    ('profit_total_project', 'Profit Total Project'),
    ('incentive', 'Insentif'),
]

RPC_PROFITABILITY_SECTIONS = [
    ('income', 'Pendapatan'),
    ('cost', 'Biaya'),
    ('result', 'Hasil'),
]


class RpcDocumentProfitabilityLine(models.Model):
    _name = 'rpc.document.profitability.line'
    _description = 'RPC Full Tenor Profitability Line'
    _order = 'document_id, sequence, id'

    document_id = fields.Many2one(
        'rpc.document', required=True, ondelete='cascade', index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='document_id.currency_id',
        store=True, readonly=True,
    )
    sequence = fields.Integer(readonly=True)
    section = fields.Selection(
        RPC_PROFITABILITY_SECTIONS,
        string='Kategori', required=True, readonly=True,
    )
    component = fields.Selection(
        RPC_PROFITABILITY_COMPONENTS,
        string='Komponen', required=True, readonly=True,
    )
    batas_atas = fields.Monetary(
        string='Batas Atas', currency_field='currency_id', readonly=True,
    )
    percentage_batas_atas = fields.Float(
        string='Persentase Batas Atas', digits=(16, 12), readonly=True,
    )
    batas_bawah = fields.Monetary(
        string='Batas Bawah', currency_field='currency_id', readonly=True,
    )
    percentage_batas_bawah = fields.Float(
        string='Persentase Batas Bawah', digits=(16, 12), readonly=True,
    )
    formula = fields.Char(string='Formula Excel', readonly=True)

    _document_component_unique = models.Constraint(
        'UNIQUE(document_id, component)',
        'Komponen profitabilitas hanya boleh muncul satu kali pada setiap RPC!',
    )


class RpcDocument(models.Model):
    _inherit = 'rpc.document'

    rpc_profitability_line_ids = fields.One2many(
        'rpc.document.profitability.line', 'document_id',
        string='Perhitungan Profitabilitas Full Tenor', copy=False,
    )

    rpc_indicator_otr_awal = fields.Monetary(
        string='OTR Awal', currency_field='currency_id',
        compute='_compute_rpc_financial_indicators',
    )
    rpc_indicator_discount_cashback = fields.Monetary(
        string='Diskon & Cashback', currency_field='currency_id',
        compute='_compute_rpc_financial_indicators',
    )
    rpc_indicator_accessories = fields.Monetary(
        string='Accessories dll', currency_field='currency_id',
        compute='_compute_rpc_financial_indicators',
    )
    rpc_indicator_dealer = fields.Char(
        string='Dealer', compute='_compute_rpc_financial_indicators',
    )

    rpc_profit_bv_batas_atas = fields.Float(
        string='Profit BV Batas Atas', digits=(16, 12),
        compute='_compute_rpc_profitability_summary',
    )
    rpc_profit_bv_batas_bawah = fields.Float(
        string='Profit BV Batas Bawah', digits=(16, 12),
        compute='_compute_rpc_profitability_summary',
    )
    rpc_profit_rpc_batas_atas = fields.Float(
        string='Profit RPC Batas Atas', digits=(16, 12),
        compute='_compute_rpc_profitability_summary',
    )
    rpc_profit_rpc_batas_bawah = fields.Float(
        string='Profit RPC Batas Bawah', digits=(16, 12),
        compute='_compute_rpc_profitability_summary',
    )
    rpc_rental_hok_batas_atas = fields.Monetary(
        string='Rental HOK Batas Atas', currency_field='currency_id',
        compute='_compute_rpc_profitability_summary',
    )
    rpc_rental_hok_batas_bawah = fields.Monetary(
        string='Rental HOK Batas Bawah', currency_field='currency_id',
        compute='_compute_rpc_profitability_summary',
    )
    rpc_hok_individual_batas_atas = fields.Monetary(
        string='Porsi Individu Batas Atas', currency_field='currency_id',
        compute='_compute_rpc_profitability_summary',
    )
    rpc_hok_individual_batas_bawah = fields.Monetary(
        string='Porsi Individu Batas Bawah', currency_field='currency_id',
        compute='_compute_rpc_profitability_summary',
    )

    @api.depends(
        'harga_otr', 'discount', 'cashback',
        'special_req_1_amount', 'special_req_2_amount',
        'special_req_3_amount', 'special_req_4_amount',
        'special_req_5_amount', 'purchase_line_ids.amount',
        'purchase_line_ids.line_type', 'dealer_line_ids.description',
        'dealer_line_ids.sequence',
    )
    def _compute_rpc_financial_indicators(self):
        for document in self:
            document.rpc_indicator_otr_awal = (
                document._get_effective_purchase_amount(
                    'harga_otr', 'harga_otr'
                )
            )
            document.rpc_indicator_discount_cashback = sum((
                document._get_effective_purchase_amount(
                    'discount', 'discount'
                ),
                document._get_effective_purchase_amount(
                    'cashback', 'cashback'
                ),
            ))
            special_request_lines = document.purchase_line_ids.filtered(
                lambda line: line.line_type
                and line.line_type.startswith('special_req_')
            )
            if special_request_lines:
                document.rpc_indicator_accessories = sum(
                    special_request_lines.mapped('amount')
                )
            else:
                document.rpc_indicator_accessories = sum((
                    document.special_req_1_amount,
                    document.special_req_2_amount,
                    document.special_req_3_amount,
                    document.special_req_4_amount,
                    document.special_req_5_amount,
                ))
            dealer_names = document.dealer_line_ids.sorted(
                key=lambda line: (line.sequence, line.id)
            ).mapped('description')
            document.rpc_indicator_dealer = ', '.join(
                filter(None, dealer_names)
            )

    def _rpc_selected_summary_amount(
        self, lines, hierarchy_1_name, hierarchy_2_name, divide_by_qty=False
    ):
        """Return the Excel tenor column from an integrated hierarchy row."""
        self.ensure_one()
        selected_lines = lines.filtered(
            lambda line: (
                line.hierarchy_1_id.name == hierarchy_1_name
                and line.hierarchy_2_id.name == hierarchy_2_name
            )
        )
        if not selected_lines or self.masa_sewa <= 0:
            return 0.0
        year_number = min(max(math.ceil(self.masa_sewa / 12.0), 1), 5)
        amount = selected_lines[:1][f'tahun_{year_number}']
        if divide_by_qty:
            return amount / self.jumlah_unit if self.jumlah_unit else 0.0
        return amount

    def _rpc_profitability_values(self):
        """Mirror the uploaded workbook's Tab RPC profitability formulas."""
        self.ensure_one()
        tenor = self.masa_sewa
        qty = self.jumlah_unit
        otr = self.otr_final

        rental_upper = self.sewa_per_bulan_batas_atas * tenor
        rental_lower = self.sewa_per_bulan_batas_bawah * tenor
        disposal = self.resale_value_rate * otr
        total_income_upper = rental_upper + disposal
        total_income_lower = rental_lower + disposal

        interest = 0.0
        if self.masa_kredit > 0:
            interest = (
                self.bunga_pct * self.masa_kredit / 12.0
                * self.pokok_hutang * tenor / self.masa_kredit
            )
        provision = self.provisi_admin_pct * self.pokok_hutang + self.fidusia
        stnk = sum(self.stnk_line_ids.mapped('amount'))
        insurance = sum(self.insurance_line_ids.mapped('amount'))
        service = sum(self.service_line_ids.mapped('amount'))
        towing = self.biaya_towing / 12.0 * tenor
        replacement = self.replacement_car_ratio * sum((
            interest, provision, stnk, insurance, service, towing, otr,
        ))

        features_upper = self._rpc_selected_summary_amount(
            self.funding_needs_batas_atas_ids,
            'AKUMULASI/UNIT', 'FITUR SEWA', divide_by_qty=True,
        )
        features_lower = self._rpc_selected_summary_amount(
            self.funding_needs_batas_bawah_ids,
            'AKUMULASI/UNIT', 'FITUR SEWA', divide_by_qty=True,
        )
        if not features_upper and not features_lower:
            year_count = math.ceil(tenor / 12.0) if tenor > 0 else 0
            feature_fallback = (
                (self.management_fee + self.free_own_risk
                 + self.asuransi_jiwa_pa) * year_count
                + self.bank_garansi_deposit
            )
            features_upper = features_lower = feature_fallback

        opex = self.opex_pusat_pct * otr * tenor / 12.0
        funding_upper = self._rpc_selected_summary_amount(
            self.gapping_cost_batas_atas_ids,
            'TOTAL FUNDING', 'Akumulasi', divide_by_qty=True,
        )
        funding_lower = self._rpc_selected_summary_amount(
            self.gapping_cost_batas_bawah_ids,
            'TOTAL FUNDING', 'Akumulasi', divide_by_qty=True,
        )
        penalty = (
            ((self.masa_kredit - tenor) / self.masa_kredit)
            * self.pokok_hutang * self.penalti_pct
            if self.masa_kredit > tenor and self.masa_kredit > 0 else 0.0
        )
        marketing_upper = self._rpc_selected_summary_amount(
            self.funding_needs_batas_atas_ids,
            'AKUMULASI/UNIT', 'MARKETING & KOMISI',
        )
        marketing_lower = self._rpc_selected_summary_amount(
            self.funding_needs_batas_bawah_ids,
            'AKUMULASI/UNIT', 'MARKETING & KOMISI',
        )
        if not marketing_upper and not marketing_lower:
            marketing_upper = marketing_lower = (
                self.total_biaya_marketing / qty if qty else 0.0
            )

        common_cost = sum((
            interest, provision, stnk, insurance, service, towing,
            replacement, opex, penalty,
        ))
        total_cost_upper = (
            common_cost + features_upper + funding_upper + marketing_upper
        )
        total_cost_lower = (
            common_cost + features_lower + funding_lower + marketing_lower
        )
        remaining_book_value = (96.0 - tenor) * (otr / 96.0)
        profit_upper = (
            total_income_upper - total_cost_upper - remaining_book_value
        )
        profit_lower = (
            total_income_lower - total_cost_lower - remaining_book_value
        )
        project_upper = profit_upper * qty
        project_lower = profit_lower * qty

        per_unit_denominator = otr
        project_denominator = otr * qty

        def ratio(amount, denominator=per_unit_denominator):
            return amount / denominator if denominator else 0.0

        values = [
            ('income', 'rental_income', rental_upper, rental_lower,
             'Sewa per Bulan × Masa Sewa'),
            ('income', 'disposal_resale', disposal, disposal,
             'Resale Value Operasional × OTR Final'),
            ('income', 'total_income', total_income_upper, total_income_lower,
             'Pendapatan Sewa + Disposal/Resale'),
            ('cost', 'interest', interest, interest,
             '(Bunga × Masa Kredit/12 × Pokok Hutang) × Tenor/Masa Kredit'),
            ('cost', 'provision', provision, provision,
             '(Provisi & Admin × Pokok Hutang) + Fidusia'),
            ('cost', 'stnk', stnk, stnk,
             'Total amount seluruh baris STNK'),
            ('cost', 'insurance', insurance, insurance,
             'Total amount seluruh baris Asuransi'),
            ('cost', 'service', service, service,
             'Total amount seluruh baris Service'),
            ('cost', 'towing', towing, towing,
             'Biaya Towing / 12 × Masa Sewa'),
            ('cost', 'replacement', replacement, replacement,
             'Rasio Replacement × (Bunga s.d. Towing + OTR Final)'),
            ('cost', 'features', features_upper, features_lower,
             'Akumulasi/Unit Fitur Sewa tahun tenor / Jumlah Unit'),
            ('cost', 'opex', opex, opex,
             'Opex Pusat × OTR Final × Masa Sewa/12'),
            ('cost', 'funding', funding_upper, funding_lower,
             'Akumulasi Gapping tahun tenor / Jumlah Unit'),
            ('cost', 'penalty', penalty, penalty,
             'Jika Tenor < Masa Kredit: sisa Pokok Hutang × Penalti'),
            ('cost', 'marketing', marketing_upper, marketing_lower,
             'Akumulasi/Unit Marketing & Komisi tahun tenor'),
            ('cost', 'total_cost', total_cost_upper, total_cost_lower,
             'Jumlah seluruh komponen biaya'),
            ('result', 'remaining_book_value', remaining_book_value,
             remaining_book_value, '(96 - Masa Sewa) × OTR Final / 96'),
            ('result', 'profit_per_unit', profit_upper, profit_lower,
             'Total Pendapatan - Total Biaya - Sisa Nilai Buku'),
            ('result', 'profit_total_project', project_upper, project_lower,
             'Profit Per Unit × Jumlah Unit'),
            ('result', 'incentive', self.insentif_jumlah_batas_atas,
             self.insentif_jumlah_batas_bawah, 'Jumlah Insentif RPC'),
        ]
        result = []
        for sequence, (section, component, upper, lower, formula) in enumerate(
            values, start=1
        ):
            denominator = (
                project_denominator
                if component in ('profit_total_project', 'incentive')
                else per_unit_denominator
            )
            result.append({
                'sequence': sequence * 10,
                'section': section,
                'component': component,
                'batas_atas': upper,
                'percentage_batas_atas': ratio(upper, denominator),
                'batas_bawah': lower,
                'percentage_batas_bawah': ratio(lower, denominator),
                'formula': formula,
            })
        return result

    def _generate_rpc_profitability_lines(self):
        line_model = self.env['rpc.document.profitability.line']
        for document in self:
            line_model.search([('document_id', '=', document.id)]).unlink()
            if document.masa_sewa <= 0 or document.otr_final <= 0:
                continue
            line_model.create([
                {'document_id': document.id, **values}
                for values in document._rpc_profitability_values()
            ])

    @api.depends(
        'masa_sewa', 'jumlah_unit', 'otr_final', 'resale_value_rate',
        'sewa_per_bulan_batas_atas', 'sewa_per_bulan_batas_bawah',
        'bunga_pct', 'masa_kredit', 'pokok_hutang', 'provisi_admin_pct',
        'fidusia', 'biaya_towing', 'replacement_car_ratio',
        'opex_pusat_pct', 'penalti_pct', 'total_biaya_marketing',
        'stnk_line_ids.amount', 'insurance_line_ids.amount',
        'service_line_ids.amount',
        'funding_needs_batas_atas_ids.tahun_1',
        'funding_needs_batas_atas_ids.tahun_2',
        'funding_needs_batas_atas_ids.tahun_3',
        'funding_needs_batas_atas_ids.tahun_4',
        'funding_needs_batas_atas_ids.tahun_5',
        'funding_needs_batas_bawah_ids.tahun_1',
        'funding_needs_batas_bawah_ids.tahun_2',
        'funding_needs_batas_bawah_ids.tahun_3',
        'funding_needs_batas_bawah_ids.tahun_4',
        'funding_needs_batas_bawah_ids.tahun_5',
        'gapping_cost_batas_atas_ids.tahun_1',
        'gapping_cost_batas_atas_ids.tahun_2',
        'gapping_cost_batas_atas_ids.tahun_3',
        'gapping_cost_batas_atas_ids.tahun_4',
        'gapping_cost_batas_atas_ids.tahun_5',
        'gapping_cost_batas_bawah_ids.tahun_1',
        'gapping_cost_batas_bawah_ids.tahun_2',
        'gapping_cost_batas_bawah_ids.tahun_3',
        'gapping_cost_batas_bawah_ids.tahun_4',
        'gapping_cost_batas_bawah_ids.tahun_5',
        'insentif_jumlah_batas_atas', 'insentif_jumlah_batas_bawah',
        'hok', 'basis_otr', 'resale_value_pct', 'buffer_hok',
    )
    def _compute_rpc_profitability_summary(self):
        for document in self:
            values = {
                line['component']: line
                for line in document._rpc_profitability_values()
            }
            profit_upper = values['profit_per_unit']['batas_atas']
            profit_lower = values['profit_per_unit']['batas_bawah']
            disposal_upper = values['disposal_resale']['batas_atas']
            disposal_lower = values['disposal_resale']['batas_bawah']
            book_upper = values['remaining_book_value']['batas_atas']
            book_lower = values['remaining_book_value']['batas_bawah']
            denominator_upper = disposal_upper + book_upper
            denominator_lower = disposal_lower + book_lower

            document.rpc_profit_bv_batas_atas = (
                profit_upper / denominator_upper if denominator_upper else 0.0
            )
            document.rpc_profit_bv_batas_bawah = (
                profit_lower / denominator_lower if denominator_lower else 0.0
            )
            document.rpc_profit_rpc_batas_atas = (
                profit_upper / document.otr_final if document.otr_final else 0.0
            )
            document.rpc_profit_rpc_batas_bawah = (
                profit_lower / document.otr_final if document.otr_final else 0.0
            )

            rental_upper = rental_lower = 0.0
            holder_upper = holder_lower = 0.0
            if (
                document.hok == 'yes'
                and document.masa_sewa > 0
                and document.otr_final > 0
            ):
                hok_values = document._hok_calculation_values()
                rental_upper = hok_values['batas_atas']['rental_per_month']
                rental_lower = hok_values['batas_bawah']['rental_per_month']
                holder_upper = hok_values['batas_atas']['hok_holder_portion']
                holder_lower = hok_values['batas_bawah']['hok_holder_portion']
            document.rpc_rental_hok_batas_atas = rental_upper
            document.rpc_rental_hok_batas_bawah = rental_lower
            document.rpc_hok_individual_batas_atas = holder_upper
            document.rpc_hok_individual_batas_bawah = holder_lower

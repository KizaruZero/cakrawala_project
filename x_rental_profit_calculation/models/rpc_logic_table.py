# -*- coding: utf-8 -*-
import math

from odoo import api, fields, models


LOGIC_FORMULAS = {
    'F01': 'total_downpayment',
    'F02': (
        '-(sewa_per_bulan - angsuran_per_bulan) '
        '* ((1 + max(masa_sewa, 12)) / 2)'
    ),
    'F03': '((TOP + offset pembayaran) / 30) * sewa_per_bulan',
    'BVK01': 'estimasi biaya STNK tahun berjalan * jumlah_unit',
    'BVK02': 'asuransi tahun berjalan * jumlah_unit',
    'BVK03': 'estimasi biaya service tahun berjalan * jumlah_unit',
    'BVK04': (
        '(akumulasi STNK + Asuransi + Service '
        '+ (otr_final * jumlah_unit * 12 / masa_sewa)) '
        '* replacement_car_ratio'
    ),
    'FT01': 'management_fee * jumlah_unit',
    'FT02': 'free_own_risk * jumlah_unit',
    'FT03': 'bank_garansi_deposit',
    'FT04': 'asuransi_jiwa_pa * jumlah_unit',
    'MK01': (
        'pic_internal * ((1 + (index_tahun * 12)) / 2) * jumlah_unit'
    ),
    'MK02': 'infrastruktur * jumlah_unit',
    'MK03': 'komisi_proyek * jumlah_unit',
    'MK04': (
        'lainnya_marketing * ((1 + horizon_bulan_tahun) / 2) '
        '* jumlah_unit'
    ),
    'OPX01': (
        '(opex_pusat_pct / 12 * otr_final) '
        '* ((1 + horizon_bulan_tahun) / 2) * jumlah_unit'
    ),
}

# These are the columns explicitly marked "ini yg dimasukin" in the XLSX.
FUNDING_ACCUMULATED_CODES = frozenset({
    'BVK01', 'BVK02', 'BVK03', 'FT01', 'FT02', 'FT04',
})
GAPPING_ACCUMULATED_CODES = frozenset({
    'BVK01', 'BVK02', 'BVK03',
})
FUNDING_LINE_MODELS = (
    'rpc.document.funding.needs.batas.atas',
    'rpc.document.gapping.cost.batas.atas',
    'rpc.document.funding.needs.batas.bawah',
    'rpc.document.gapping.cost.batas.bawah',
)


class RpcLogicTable(models.Model):
    _name = 'logic.table'
    _description = 'RPC Logic Table'
    _order = 'document_id, sequence, tahun, id'

    document_id = fields.Many2one(
        'rpc.document',
        string='RPC Document',
        required=True,
        ondelete='cascade',
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='document_id.currency_id',
        store=True,
        readonly=True,
    )
    logic_id = fields.Many2one(
        'rpc.hierarchy.logic',
        string='Hierarchy Logic Table',
        required=True,
        ondelete='restrict',
        index=True,
        readonly=True,
    )
    hierarchy_id = fields.Many2one(
        'rpc.hierarchy.logic.hierarchy',
        string='Hierarchy',
        related='logic_id.hierarchy_id',
        store=True,
        readonly=True,
    )
    cost_group_code_id = fields.Many2one(
        'rpc.hierarchy.logic.cost.group.code',
        string='Cost Group Code',
        related='logic_id.cost_group_code_id',
        store=True,
        readonly=True,
    )
    cost_group_name_id = fields.Many2one(
        'rpc.hierarchy.logic.cost.group.name',
        string='Cost Group Name',
        related='logic_id.cost_group_name_id',
        store=True,
        readonly=True,
    )
    payment_schedule_id = fields.Many2one(
        'rpc.hierarchy.logic.payment.schedule',
        string='Jadwal Pembayaran',
        related='logic_id.payment_schedule_id',
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(string='Urutan', readonly=True)
    year_index = fields.Integer(string='Index Tahun', readonly=True)
    tahun = fields.Integer(string='Tahun', readonly=True, index=True)
    formula = fields.Char(string='Formula', readonly=True)
    variable = fields.Char(string='Variable', readonly=True)
    masa_sewa = fields.Integer(string='Masa Sewa (Bulan)', readonly=True)
    masa_kredit = fields.Integer(string='Masa Kredit (Bulan)', readonly=True)
    qty_unit = fields.Integer(string='Qty Unit', readonly=True)
    gapping_pct = fields.Float(
        string='Gapping (%)',
        readonly=True,
        digits=(5, 4),
    )

    harga_per_unit_year_batas_atas = fields.Monetary(
        string='Harga/Unit/Year Batas Atas',
        currency_field='currency_id',
        readonly=True,
    )
    harga_per_unit_year_batas_bawah = fields.Monetary(
        string='Harga/Unit/Year Batas Bawah',
        currency_field='currency_id',
        readonly=True,
    )
    akumulasi_per_unit_batas_atas = fields.Monetary(
        string='Akumulasi/Unit Batas Atas',
        currency_field='currency_id',
        readonly=True,
    )
    akumulasi_per_unit_batas_bawah = fields.Monetary(
        string='Akumulasi/Unit Batas Bawah',
        currency_field='currency_id',
        readonly=True,
    )
    total_year_batas_atas = fields.Monetary(
        string='Total/Year Batas Atas',
        currency_field='currency_id',
        readonly=True,
    )
    total_year_batas_bawah = fields.Monetary(
        string='Total/Year Batas Bawah',
        currency_field='currency_id',
        readonly=True,
    )
    akumulasi_total_batas_atas = fields.Monetary(
        string='Akumulasi Total Batas Atas',
        currency_field='currency_id',
        readonly=True,
    )
    akumulasi_total_batas_bawah = fields.Monetary(
        string='Akumulasi Total Batas Bawah',
        currency_field='currency_id',
        readonly=True,
    )
    gapping_total_year_batas_atas = fields.Monetary(
        string='Gapping Total/Year Batas Atas',
        currency_field='currency_id',
        readonly=True,
    )
    gapping_total_year_batas_bawah = fields.Monetary(
        string='Gapping Total/Year Batas Bawah',
        currency_field='currency_id',
        readonly=True,
    )
    akumulasi_gapping_total_batas_atas = fields.Monetary(
        string='Akumulasi Gapping Total Batas Atas',
        currency_field='currency_id',
        readonly=True,
    )
    akumulasi_gapping_total_batas_bawah = fields.Monetary(
        string='Akumulasi Gapping Total Batas Bawah',
        currency_field='currency_id',
        readonly=True,
    )

    _document_logic_year_unique = models.Constraint(
        'UNIQUE(document_id, logic_id, tahun)',
        'Hierarchy Logic dan Tahun hanya boleh muncul satu kali pada setiap dokumen RPC!',
    )


class RpcDocument(models.Model):
    _inherit = 'rpc.document'

    logic_table_ids = fields.One2many(
        'logic.table',
        'document_id',
        string='Logic Table',
        copy=False,
    )
    logic_table_count = fields.Integer(
        string='Logic Table Count',
        compute='_compute_logic_table_count',
    )

    @api.depends('logic_table_ids')
    def _compute_logic_table_count(self):
        for document in self:
            document.logic_table_count = len(document.logic_table_ids)

    def action_view_logic_table(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'x_rental_profit_calculation.action_rpc_logic_table'
        )
        action['domain'] = [('document_id', '=', self.id)]
        action['context'] = {
            'default_document_id': self.id,
            'create': False,
            'edit': False,
            'delete': False,
        }
        return action

    def _logic_year_line_amount(self, lines, year, year_index):
        """Return a yearly amount by year, with sequence as legacy fallback."""
        self.ensure_one()
        ordered_lines = lines.sorted(
            lambda line: (line.tahun, line.sequence, line.id)
        )
        matching_line = ordered_lines.filtered(
            lambda line: line.tahun == year
        )[:1]
        if matching_line:
            return matching_line.amount
        if year_index < len(ordered_lines):
            return ordered_lines[year_index].amount
        return 0.0

    def _logic_cumulative_vehicle_cost(self, year, year_index):
        """Return accumulated STNK, insurance, and service through a year."""
        self.ensure_one()
        start_year = year - year_index
        accumulated_amount = 0.0
        for cost_year_index in range(year_index + 1):
            cost_year = start_year + cost_year_index
            accumulated_amount += self._logic_year_line_amount(
                self.stnk_line_ids, cost_year, cost_year_index
            )
            accumulated_amount += self._logic_year_line_amount(
                self.insurance_line_ids, cost_year, cost_year_index
            )
            accumulated_amount += self._logic_year_line_amount(
                self.service_line_ids, cost_year, cost_year_index
            )
        return accumulated_amount * self.jumlah_unit

    def _logic_table_amounts(self, code, year, year_index, year_count):
        """Return unit and yearly totals for upper and lower limits."""
        self.ensure_one()
        qty = self.jumlah_unit
        upper_unit = lower_unit = 0.0
        upper_total = lower_total = 0.0

        if code == 'F01':
            upper_unit = lower_unit = self.total_downpayment
            credit_year_count = (
                math.ceil(self.masa_kredit / 12.0)
                if self.masa_kredit > 0 else 0
            )
            if year_index < credit_year_count:
                upper_total = lower_total = self.total_downpayment * qty
        elif code == 'F02':
            installment_due = self._logic_installment_due()
            upper_total = self._logic_rent_gap_amount(
                'batas_atas', installment_due, year_index
            )
            lower_total = self._logic_rent_gap_amount(
                'batas_bawah', installment_due, year_index
            )
        elif code == 'F03':
            upper_total = self._logic_top_amount('batas_atas')
            lower_total = self._logic_top_amount('batas_bawah')
        elif code == 'BVK01':
            annual_amount = self._logic_year_line_amount(
                self.stnk_line_ids, year, year_index
            )
            upper_total = lower_total = annual_amount * qty
        elif code == 'BVK02':
            annual_amount = self._logic_year_line_amount(
                self.insurance_line_ids, year, year_index
            )
            upper_total = lower_total = annual_amount * qty
        elif code == 'BVK03':
            annual_amount = self._logic_year_line_amount(
                self.service_line_ids, year, year_index
            )
            upper_total = lower_total = annual_amount * qty
        elif code == 'BVK04':
            accumulated_vehicle_cost = self._logic_cumulative_vehicle_cost(
                year, year_index
            )
            annual_vehicle_total = (
                self.otr_final * qty * 12.0 / self.masa_sewa
                if self.masa_sewa else 0.0
            )
            replacement_ratio = (
                1.0 / self.replacement_car_qty
                if self.replacement_car_qty else 0.0
            )
            upper_total = lower_total = (
                accumulated_vehicle_cost + annual_vehicle_total
            ) * replacement_ratio
        elif code == 'FT01':
            upper_total = lower_total = self.management_fee * qty
        elif code == 'FT02':
            upper_total = lower_total = self.free_own_risk * qty
        elif code == 'FT03':
            upper_total = lower_total = self.bank_garansi_deposit
        elif code == 'FT04':
            upper_total = lower_total = self.asuransi_jiwa_pa * qty
        elif code == 'MK01':
            month_horizon = min(self.masa_sewa, (year_index + 1) * 12)
            upper_total = lower_total = (
                self.pic_internal * (1.0 + month_horizon) / 2.0 * qty
            )
        elif code == 'MK02':
            upper_total = lower_total = self.infrastruktur * qty
        elif code == 'MK03':
            upper_total = lower_total = self.komisi_proyek * qty
        elif code == 'MK04':
            month_horizon = min(self.masa_sewa, (year_index + 1) * 12)
            upper_total = lower_total = (
                self.lainnya_marketing
                * (1.0 + month_horizon)
                / 2.0
                * qty
            )
        elif code == 'OPX01':
            month_horizon = min(self.masa_sewa, (year_index + 1) * 12)
            monthly_opex = self.opex_pusat_pct * self.otr_final / 12.0
            upper_total = lower_total = (
                monthly_opex * (1.0 + month_horizon) / 2.0 * qty
            )

        return upper_unit, lower_unit, upper_total, lower_total

    def _logic_rent_gap_amount(self, limit_type, payment_due, year_index):
        """Mirror Excel rows 140-142 for the selected rental limit."""
        self.ensure_one()
        rent_amount = (
            self.sewa_per_bulan_batas_atas
            if limit_type == 'batas_atas'
            else self.sewa_per_bulan_batas_bawah
        )
        year_horizon = (year_index + 1) * 12
        if payment_due == 'addm':
            month_horizon = max(self.masa_sewa, year_horizon)
        else:
            month_horizon = (
                self.masa_sewa
                if self.masa_sewa > year_horizon
                else year_horizon - 1
            )
        return -(
            rent_amount - self.angsuran_per_bulan
        ) * (1.0 + month_horizon) / 2.0

    def _logic_installment_due(self):
        """Return ADDM/ADDB from Excel cell AI17 (Jenis Angsuran)."""
        self.ensure_one()
        installment_name = (
            self.jenis_angsuran_id.name or ''
        ).strip().lower()
        return 'addm' if installment_name == 'addm' else 'addb'

    def _logic_top_amount(self, limit_type):
        """Mirror Excel row 143 (Check TOP 1)."""
        self.ensure_one()
        rent_amount = (
            self.sewa_per_bulan_batas_atas
            if limit_type == 'batas_atas'
            else self.sewa_per_bulan_batas_bawah
        )
        payment_offset = 0 if self.term_of_payment_due == 'addm' else 30
        return (
            (self.term_of_payment_hari + payment_offset) / 30.0
        ) * rent_amount

    def _logic_gapping_factor(self, code, payment_schedule, year_index):
        self.ensure_one()
        if code == 'F01':
            lease_year_count = math.ceil(self.masa_sewa / 12.0)
            return 1.0 if year_index < lease_year_count else 0.0
        if code == 'F02':
            return year_index + 0.5
        if code == 'BVK02':
            return 300.0 / 360.0
        if (
            code in ('BVK03', 'BVK04')
            and year_index == 0
            and self.masa_sewa < 12
        ):
            return self.masa_sewa / 12.0
        if code in ('FT02', 'MK01', 'MK04'):
            return 0.5
        if code == 'OPX01':
            return 0.5 if year_index == 0 else 1.0
        return 1.0

    def _clear_funding_and_gapping_lines(self):
        for document in self:
            for model_name in FUNDING_LINE_MODELS:
                self.env[model_name].search([
                    ('document_id', '=', document.id),
                ]).unlink()

    def _sync_funding_hierarchy_chain(self, logic):
        """Mirror an active Hierarchy Logic chain into the legacy funding masters."""
        hierarchy_1_model = self.env['rpc.funding.hierarchy.1'].with_context(
            active_test=False
        )
        hierarchy_2_model = self.env['rpc.funding.hierarchy.2'].with_context(
            active_test=False
        )
        hierarchy_3_model = self.env['rpc.funding.hierarchy.3'].with_context(
            active_test=False
        )

        hierarchy_name = (logic.hierarchy_id.name or '').strip()
        code = (logic.cost_group_code_id.name or '').strip()
        cost_group_name = (logic.cost_group_name_id.name or '').strip()

        hierarchy_1 = hierarchy_1_model.search([
            ('name', '=', hierarchy_name),
        ], limit=1)
        hierarchy_1_values = {
            'sequence': logic.hierarchy_id.sequence,
            'active': True,
        }
        if hierarchy_1:
            hierarchy_1.write(hierarchy_1_values)
        else:
            hierarchy_1 = hierarchy_1_model.create({
                'name': hierarchy_name,
                **hierarchy_1_values,
            })

        hierarchy_2 = hierarchy_2_model.search([
            ('hierarchy_1_id', '=', hierarchy_1.id),
            ('name', '=', code),
        ], limit=1)
        hierarchy_2_values = {
            'code': code,
            'sequence': logic.cost_group_code_id.sequence,
            'active': True,
        }
        if hierarchy_2:
            hierarchy_2.write(hierarchy_2_values)
        else:
            hierarchy_2 = hierarchy_2_model.create({
                'name': code,
                'hierarchy_1_id': hierarchy_1.id,
                **hierarchy_2_values,
            })

        hierarchy_3 = hierarchy_3_model.search([
            ('hierarchy_2_id', '=', hierarchy_2.id),
            ('name', '=', cost_group_name),
        ], limit=1)
        hierarchy_3_values = {
            'code': code,
            'sequence': logic.cost_group_name_id.sequence,
            'active': True,
        }
        if hierarchy_3:
            hierarchy_3.write(hierarchy_3_values)
        else:
            hierarchy_3 = hierarchy_3_model.create({
                'name': cost_group_name,
                'hierarchy_2_id': hierarchy_2.id,
                **hierarchy_3_values,
            })

        return hierarchy_1, hierarchy_2, hierarchy_3

    def _sync_summary_hierarchy(self, hierarchy_name, line_name, sequence):
        """Create the H1/H2 pair used by integrated Excel summary rows."""
        hierarchy_1_model = self.env['rpc.funding.hierarchy.1'].with_context(
            active_test=False
        )
        hierarchy_2_model = self.env['rpc.funding.hierarchy.2'].with_context(
            active_test=False
        )
        hierarchy_1 = hierarchy_1_model.search([
            ('name', '=', hierarchy_name),
        ], limit=1)
        hierarchy_1_values = {'sequence': 170, 'active': True}
        if hierarchy_1:
            hierarchy_1.write(hierarchy_1_values)
        else:
            hierarchy_1 = hierarchy_1_model.create({
                'name': hierarchy_name,
                **hierarchy_1_values,
            })

        hierarchy_2 = self.env['rpc.funding.hierarchy.2']
        if line_name:
            hierarchy_2 = hierarchy_2_model.search([
                ('hierarchy_1_id', '=', hierarchy_1.id),
                ('name', '=', line_name),
            ], limit=1)
            hierarchy_2_values = {
                'code': line_name,
                'sequence': 160 + sequence,
                'active': True,
            }
            if hierarchy_2:
                hierarchy_2.write(hierarchy_2_values)
            else:
                hierarchy_2 = hierarchy_2_model.create({
                    'name': line_name,
                    'hierarchy_1_id': hierarchy_1.id,
                    **hierarchy_2_values,
                })
        return hierarchy_1, hierarchy_2

    def _summary_values(
        self, sequence, name, year_values, formula, total=None
    ):
        """Build a normalized summary line from the five Excel year columns."""
        self.ensure_one()
        values = {
            'sequence': sequence,
            'summary_name': name,
            'formula': formula,
        }
        normalized_values = list(year_values[:5])
        normalized_values.extend([0.0] * (5 - len(normalized_values)))
        for year_number, amount in enumerate(normalized_values, start=1):
            values[f'tahun_{year_number}'] = amount
        values['total'] = sum(normalized_values) if total is None else total
        return values

    def _funding_summary_values(self, values_by_code):
        """Mirror Excel rows 107-114 under the AKUMULASI/UNIT hierarchy."""
        self.ensure_one()
        qty = self.jumlah_unit

        def code_values(code):
            return values_by_code.get(code, [0.0] * 5)

        def sum_codes(*codes):
            return [
                sum(code_values(code)[index] for code in codes)
                for index in range(5)
            ]

        def accumulated_per_unit(code):
            accumulated = 0.0
            result = []
            for amount in code_values(code):
                if qty and amount > 0:
                    accumulated += amount / qty
                    result.append(accumulated)
                else:
                    result.append(0.0)
            return result

        stnk = accumulated_per_unit('BVK01')
        insurance = accumulated_per_unit('BVK02')
        service = accumulated_per_unit('BVK03')

        replacement = []
        accumulated_replacement = 0.0
        for index, amount in enumerate(code_values('BVK04')):
            if qty and (stnk[index] + insurance[index] + service[index]) > 0:
                accumulated_replacement += amount / qty
                replacement.append(accumulated_replacement)
            else:
                replacement.append(0.0)

        marketing_year = sum_codes('MK01', 'MK02', 'MK03', 'MK04')
        lumpsum = [0.0] * 5
        if qty:
            lumpsum[0] = (
                code_values('MK02')[0] + code_values('MK03')[0]
            ) / qty

        marketing = []
        accumulated_marketing = 0.0
        for amount in marketing_year:
            if qty and amount > 0:
                accumulated_marketing += amount / qty
                marketing.append(accumulated_marketing)
            else:
                marketing.append(lumpsum[0])

        feature_year = sum_codes('FT01', 'FT02', 'FT03', 'FT04')
        feature = []
        accumulated_feature = 0.0
        for amount in feature_year:
            if qty and amount > 0:
                accumulated_feature += amount / qty
                feature.append(accumulated_feature)
            else:
                feature.append(0.0)

        monthly = [
            amount / qty if qty and amount > 0 else 0.0
            for amount in sum_codes('MK01', 'MK04')
        ]

        return [
            self._summary_values(
                10, 'STNK', stnk,
                'Jika STNK > 0: STNK Funding / Jumlah Unit + akumulasi sebelumnya',
            ),
            self._summary_values(
                20, 'ASURANSI', insurance,
                'Jika Asuransi > 0: Asuransi Funding / Jumlah Unit + akumulasi sebelumnya',
            ),
            self._summary_values(
                30, 'SERVICE', service,
                'Jika Service > 0: Service Funding / Jumlah Unit + akumulasi sebelumnya',
            ),
            self._summary_values(
                40, 'REPLACEMENT CAR', replacement,
                'Replacement Car / Jumlah Unit + akumulasi sebelumnya',
            ),
            self._summary_values(
                50, 'MARKETING & KOMISI', marketing,
                'Total MK01-MK04 / Jumlah Unit + akumulasi sebelumnya',
            ),
            self._summary_values(
                60, 'FITUR SEWA', feature,
                'Total FT01-FT04 / Jumlah Unit + akumulasi sebelumnya',
            ),
            self._summary_values(
                70, 'Lumpsum/unit', lumpsum,
                '(Infrastruktur + Komisi Proyek) / Jumlah Unit',
            ),
            self._summary_values(
                80, 'Bulanan', monthly,
                '(PIC Internal + Lainnya) / Jumlah Unit',
            ),
        ]

    def _gapping_summary_values(self, limit_type, values_by_code):
        """Mirror Excel rows 137-144 (row 139 is intentionally blank)."""
        self.ensure_one()
        total_funding = [
            sum(amounts[index] for amounts in values_by_code.values())
            for index in range(5)
        ]
        accumulated = []
        running_total = 0.0
        for amount in total_funding:
            running_total += amount
            accumulated.append(running_total)

        check_addm = [
            self._logic_rent_gap_amount(limit_type, 'addm', index)
            for index in range(5)
        ]
        check_addb = [
            self._logic_rent_gap_amount(limit_type, 'addb', index)
            for index in range(5)
        ]
        selected_rent_gap = (
            check_addm
            if self._logic_installment_due() == 'addm'
            else check_addb
        )
        check_top_1 = self._logic_top_amount(limit_type)
        check_top_2 = (
            check_top_1 * self.masa_sewa
            if self.masa_sewa < 12
            else check_top_1
        )

        return [
            self._summary_values(
                10, 'TOTAL FUNDING', total_funding,
                'Jumlah seluruh baris Gapping Cost per tahun',
                total=sum(total_funding),
            ),
            self._summary_values(
                20, 'Akumulasi', accumulated,
                'Total Funding tahun berjalan + akumulasi tahun sebelumnya',
                total=0.0,
            ),
            self._summary_values(
                30, 'Selisih Sewa dipakai', selected_rent_gap,
                'Check ADDM jika Jenis Angsuran ADDM; selain itu Check ADDB',
                total=0.0,
            ),
            self._summary_values(
                40, 'Check Selisih Sewa dgn Angsuran 1 - ADDM',
                check_addm,
                '-(Sewa - Angsuran) * (1 + horizon ADDM) / 2',
                total=0.0,
            ),
            self._summary_values(
                50, 'Check Selisih Sewa dgn Angsuran 2 - ADDB',
                check_addb,
                '-(Sewa - Angsuran) * (1 + horizon ADDB) / 2',
                total=0.0,
            ),
            self._summary_values(
                60, 'Check TOP 1', [check_top_1, 0, 0, 0, 0],
                '((TOP + offset pembayaran) / 30) * Sewa per Bulan',
                total=0.0,
            ),
            self._summary_values(
                70, 'Check TOP 2', [check_top_2, 0, 0, 0, 0],
                'Jika tenor < 12 bulan: Check TOP 1 * tenor; selain itu Check TOP 1',
                total=0.0,
            ),
        ]

    def _generate_funding_and_gapping_lines(self, logic_records=None):
        """Generate the four yearly summary tables from Logic Table values."""
        logic_records = logic_records or self.env['rpc.hierarchy.logic'].search(
            [('active', '=', True)], order='sequence, id'
        )
        generatable_documents = self.filtered(
            lambda document: (
                document.tahun_mulai_sewa > 0
                and document.masa_sewa > 0
            )
        )
        generatable_documents._clear_funding_and_gapping_lines()
        hierarchy_by_logic = {
            logic.id: self._sync_funding_hierarchy_chain(logic)
            for logic in logic_records
        }

        model_specs = (
            (
                'rpc.document.funding.needs.batas.atas',
                'funding',
                'batas_atas',
            ),
            (
                'rpc.document.gapping.cost.batas.atas',
                'gapping',
                'batas_atas',
            ),
            (
                'rpc.document.funding.needs.batas.bawah',
                'funding',
                'batas_bawah',
            ),
            (
                'rpc.document.gapping.cost.batas.bawah',
                'gapping',
                'batas_bawah',
            ),
        )

        for document in generatable_documents:
            logic_lines = document.logic_table_ids.sorted(
                lambda line: (line.tahun, line.sequence, line.id)
            )
            base_year = (
                min(logic_lines.mapped('tahun'))
                if logic_lines
                else document.tahun_mulai_sewa
            )

            lines_by_logic = {}
            for line in logic_lines:
                lines_by_logic.setdefault(line.logic_id.id, []).append(line)

            values_by_model = {model_name: [] for model_name, _, _ in model_specs}
            amounts_by_model_code = {
                model_name: {} for model_name, _, _ in model_specs
            }
            for logic in logic_records:
                code = (logic.cost_group_code_id.name or '').strip().upper()
                hierarchy_1, hierarchy_2, hierarchy_3 = hierarchy_by_logic[
                    logic.id
                ]
                base_values = {
                    'document_id': document.id,
                    'sequence': logic.sequence,
                    'hierarchy_1_id': hierarchy_1.id,
                    'hierarchy_2_id': hierarchy_2.id,
                    'hierarchy_3_id': hierarchy_3.id,
                    'formula': LOGIC_FORMULAS.get(code, logic.formula),
                }

                for model_name, output_type, limit_type in model_specs:
                    values = {
                        **base_values,
                        'tahun_1': 0.0,
                        'tahun_2': 0.0,
                        'tahun_3': 0.0,
                        'tahun_4': 0.0,
                        'tahun_5': 0.0,
                    }
                    if output_type == 'funding':
                        source_prefix = (
                            'akumulasi_total'
                            if code in FUNDING_ACCUMULATED_CODES
                            else 'total_year'
                        )
                    else:
                        source_prefix = (
                            'akumulasi_gapping_total'
                            if code in GAPPING_ACCUMULATED_CODES
                            else 'gapping_total_year'
                        )
                    source_field = f'{source_prefix}_{limit_type}'

                    for logic_line in lines_by_logic.get(logic.id, []):
                        year_number = logic_line.tahun - base_year + 1
                        if 1 <= year_number <= 5:
                            values[f'tahun_{year_number}'] = logic_line[
                                source_field
                            ]
                    values['total'] = sum(
                        values[f'tahun_{year_number}']
                        for year_number in range(1, 6)
                    )
                    values_by_model[model_name].append(values)
                    amounts_by_model_code[model_name][code] = [
                        values[f'tahun_{year_number}']
                        for year_number in range(1, 6)
                    ]

            summary_specs = (
                (
                    'rpc.document.funding.needs.batas.atas',
                    'AKUMULASI/UNIT',
                    'batas_atas',
                    'funding',
                ),
                (
                    'rpc.document.gapping.cost.batas.atas',
                    'TOTAL FUNDING',
                    'batas_atas',
                    'gapping',
                ),
                (
                    'rpc.document.funding.needs.batas.bawah',
                    'AKUMULASI/UNIT',
                    'batas_bawah',
                    'funding',
                ),
                (
                    'rpc.document.gapping.cost.batas.bawah',
                    'TOTAL FUNDING',
                    'batas_bawah',
                    'gapping',
                ),
            )
            for model_name, hierarchy_name, limit_type, summary_type in summary_specs:
                amounts_by_code = amounts_by_model_code[model_name]
                if summary_type == 'funding':
                    summary_rows = document._funding_summary_values(
                        amounts_by_code
                    )
                else:
                    summary_rows = document._gapping_summary_values(
                        limit_type, amounts_by_code
                    )
                for summary_row in summary_rows:
                    summary_name = summary_row.pop('summary_name')
                    relative_sequence = summary_row['sequence']
                    hierarchy_2_name = (
                        False
                        if summary_type == 'gapping'
                        and summary_name == 'TOTAL FUNDING'
                        else summary_name
                    )
                    hierarchy_1, hierarchy_2 = (
                        document._sync_summary_hierarchy(
                            hierarchy_name,
                            hierarchy_2_name,
                            relative_sequence,
                        )
                    )
                    values_by_model[model_name].append({
                        **summary_row,
                        'document_id': document.id,
                        'sequence': 160 + relative_sequence,
                        'hierarchy_1_id': hierarchy_1.id,
                        'hierarchy_2_id': hierarchy_2.id,
                        'hierarchy_3_id': False,
                    })

            for model_name, values_list in values_by_model.items():
                if values_list:
                    self.env[model_name].create(values_list)

    def _generate_logic_table_lines(self):
        line_model = self.env['logic.table']
        logic_records = self.env['rpc.hierarchy.logic'].search(
            [('active', '=', True)], order='sequence, id'
        )
        financial_codes = {'F01', 'F02', 'F03'}
        no_total_accumulation_codes = financial_codes | {
            'BVK04', 'MK04', 'OPX01',
        }
        no_gapping_accumulation_codes = financial_codes
        accumulated_gapping_base_codes = {'FT01', 'FT02'}

        for document in self:
            line_model.search([('document_id', '=', document.id)]).unlink()
            if document.tahun_mulai_sewa <= 0 or document.masa_sewa <= 0:
                continue

            lease_year_count = math.ceil(document.masa_sewa / 12.0)
            credit_year_count = (
                math.ceil(document.masa_kredit / 12.0)
                if document.masa_kredit > 0 else 0
            )
            values_list = []

            for logic in logic_records:
                code = (logic.cost_group_code_id.name or '').strip().upper()
                if code == 'F01':
                    year_count = max(credit_year_count, lease_year_count)
                elif code == 'F02':
                    year_count = credit_year_count
                elif code == 'F03':
                    year_count = lease_year_count
                elif code == 'BVK01':
                    year_count = len(document.stnk_line_ids)
                elif code == 'BVK02':
                    year_count = len(document.insurance_line_ids)
                elif code == 'BVK03':
                    year_count = len(document.service_line_ids)
                else:
                    year_count = lease_year_count
                accum_unit_upper = accum_unit_lower = 0.0
                accum_total_upper = accum_total_lower = 0.0
                accum_gapping_upper = accum_gapping_lower = 0.0
                first_total_upper = first_total_lower = 0.0

                for year_index in range(year_count):
                    year = document.tahun_mulai_sewa + year_index
                    (
                        unit_upper,
                        unit_lower,
                        total_upper,
                        total_lower,
                    ) = document._logic_table_amounts(
                        code, year, year_index, year_count
                    )
                    accum_unit_upper += unit_upper
                    accum_unit_lower += unit_lower
                    accum_total_upper += total_upper
                    accum_total_lower += total_lower
                    if year_index == 0:
                        first_total_upper = total_upper
                        first_total_lower = total_lower

                    gapping_factor = document._logic_gapping_factor(
                        code, logic.payment_schedule_id.name, year_index
                    )
                    if code in ('F01', 'MK04'):
                        gapping_base_upper = first_total_upper
                        gapping_base_lower = first_total_lower
                    else:
                        gapping_base_upper = (
                            accum_total_upper
                            if code in accumulated_gapping_base_codes
                            else total_upper
                        )
                        gapping_base_lower = (
                            accum_total_lower
                            if code in accumulated_gapping_base_codes
                            else total_lower
                        )
                    gapping_upper = (
                        gapping_base_upper
                        * document.cost_of_fund_pct
                        * gapping_factor
                    )
                    gapping_lower = (
                        gapping_base_lower
                        * document.cost_of_fund_pct
                        * gapping_factor
                    )
                    accum_gapping_upper += gapping_upper
                    accum_gapping_lower += gapping_lower

                    values_list.append({
                        'document_id': document.id,
                        'logic_id': logic.id,
                        'sequence': logic.sequence * 100 + year_index,
                        'year_index': year_index + 1,
                        'tahun': year,
                        'formula': LOGIC_FORMULAS.get(code, logic.formula),
                        'variable': code,
                        'masa_sewa': document.masa_sewa,
                        'masa_kredit': document.masa_kredit,
                        'qty_unit': document.jumlah_unit,
                        'gapping_pct': document.cost_of_fund_pct,
                        'harga_per_unit_year_batas_atas': unit_upper,
                        'harga_per_unit_year_batas_bawah': unit_lower,
                        'akumulasi_per_unit_batas_atas': (
                            accum_unit_upper if code == 'F01' else 0.0
                        ),
                        'akumulasi_per_unit_batas_bawah': (
                            accum_unit_lower if code == 'F01' else 0.0
                        ),
                        'total_year_batas_atas': total_upper,
                        'total_year_batas_bawah': total_lower,
                        'akumulasi_total_batas_atas': (
                            0.0
                            if code in no_total_accumulation_codes
                            else accum_total_upper
                        ),
                        'akumulasi_total_batas_bawah': (
                            0.0
                            if code in no_total_accumulation_codes
                            else accum_total_lower
                        ),
                        'gapping_total_year_batas_atas': gapping_upper,
                        'gapping_total_year_batas_bawah': gapping_lower,
                        'akumulasi_gapping_total_batas_atas': (
                            0.0
                            if code in no_gapping_accumulation_codes
                            else accum_gapping_upper
                        ),
                        'akumulasi_gapping_total_batas_bawah': (
                            0.0
                            if code in no_gapping_accumulation_codes
                            else accum_gapping_lower
                        ),
                    })

            if values_list:
                line_model.create(values_list)

        self._generate_funding_and_gapping_lines(logic_records=logic_records)

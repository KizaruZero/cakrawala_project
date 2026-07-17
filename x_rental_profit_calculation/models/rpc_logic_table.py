# -*- coding: utf-8 -*-
import math

from odoo import fields, models


LOGIC_FORMULAS = {
    'F01': 'total_downpayment * jumlah_unit',
    'F02': '-(sewa_per_bulan - angsuran_per_bulan) * ((1 + masa_sewa) / 2)',
    'F03': '((TOP + offset pembayaran) / 30) * sewa_per_bulan',
    'BVK01': 'estimasi biaya STNK tahun berjalan * jumlah_unit',
    'BVK02': 'asuransi tahun berjalan * jumlah_unit',
    'BVK03': 'estimasi biaya service tahun berjalan * jumlah_unit',
    'BVK04': 'biaya replacement car per unit * jumlah_unit',
    'FT01': 'management_fee * jumlah_unit',
    'FT02': 'free_own_risk * jumlah_unit',
    'FT03': 'bank_garansi_deposit * jumlah_unit (tahun pertama)',
    'FT04': 'asuransi_jiwa_pa selama tenor / jumlah tahun * jumlah_unit',
    'MK01': 'pic_internal * 12 bulan * jumlah_unit',
    'MK02': 'infrastruktur lumpsum (tahun pertama)',
    'MK03': 'komisi_proyek lumpsum (tahun pertama)',
    'MK04': 'lainnya_marketing * 12 bulan',
}


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

    def _logic_table_amounts(self, code, year, year_index, year_count):
        """Return unit and yearly totals for upper and lower limits."""
        self.ensure_one()
        qty = self.jumlah_unit
        upper_unit = lower_unit = 0.0
        upper_total = lower_total = 0.0

        if code == 'F01':
            upper_unit = lower_unit = self.total_downpayment
            upper_total = lower_total = self.total_downpayment * qty
        elif code == 'F02':
            month_count = 12 if self.masa_sewa <= 12 else self.masa_sewa
            multiplier = (1.0 + month_count) / 2.0
            upper_total = -(
                self.sewa_per_bulan_batas_atas - self.angsuran_per_bulan
            ) * multiplier
            lower_total = -(
                self.sewa_per_bulan_batas_bawah - self.angsuran_per_bulan
            ) * multiplier
        elif code == 'F03':
            payment_offset = 0 if self.term_of_payment_due == 'addm' else 30
            multiplier = (
                (self.term_of_payment_hari + payment_offset) / 30.0
            )
            upper_total = self.sewa_per_bulan_batas_atas * multiplier
            lower_total = self.sewa_per_bulan_batas_bawah * multiplier
        elif code == 'BVK01':
            upper_unit = lower_unit = self._logic_year_line_amount(
                self.stnk_line_ids, year, year_index
            )
            upper_total = lower_total = upper_unit * qty
        elif code == 'BVK02':
            upper_unit = lower_unit = self._logic_year_line_amount(
                self.insurance_line_ids, year, year_index
            )
            upper_total = lower_total = upper_unit * qty
        elif code == 'BVK03':
            upper_unit = lower_unit = self._logic_year_line_amount(
                self.service_line_ids, year, year_index
            )
            upper_total = lower_total = upper_unit * qty
        elif code == 'BVK04':
            stnk = self._logic_year_line_amount(
                self.stnk_line_ids, year, year_index
            )
            insurance = self._logic_year_line_amount(
                self.insurance_line_ids, year, year_index
            )
            service = self._logic_year_line_amount(
                self.service_line_ids, year, year_index
            )
            annual_vehicle_cost = (
                self.otr_final * 12.0 / self.masa_sewa
                if self.masa_sewa else 0.0
            )
            upper_unit = lower_unit = (
                stnk + insurance + service + annual_vehicle_cost
            ) * self.replacement_car_ratio
            upper_total = lower_total = upper_unit * qty
        elif code == 'FT01':
            upper_unit = lower_unit = self.management_fee
            upper_total = lower_total = upper_unit * qty
        elif code == 'FT02':
            upper_unit = lower_unit = self.free_own_risk
            upper_total = lower_total = upper_unit * qty
        elif code == 'FT03' and year_index == 0:
            upper_unit = lower_unit = self.bank_garansi_deposit
            upper_total = lower_total = upper_unit * qty
        elif code == 'FT04':
            upper_unit = lower_unit = (
                self.asuransi_jiwa_pa / year_count if year_count else 0.0
            )
            upper_total = lower_total = upper_unit * qty
        elif code == 'MK01':
            upper_unit = lower_unit = self.pic_internal * 12.0
            upper_total = lower_total = upper_unit * qty
        elif code == 'MK02' and year_index == 0:
            upper_total = lower_total = self.infrastruktur
            upper_unit = lower_unit = upper_total / qty if qty else 0.0
        elif code == 'MK03' and year_index == 0:
            upper_total = lower_total = self.komisi_proyek
            upper_unit = lower_unit = upper_total / qty if qty else 0.0
        elif code == 'MK04':
            upper_total = lower_total = self.lainnya_marketing * 12.0
            upper_unit = lower_unit = upper_total / qty if qty else 0.0

        return upper_unit, lower_unit, upper_total, lower_total

    def _logic_gapping_factor(self, code, payment_schedule, year_index):
        self.ensure_one()
        if code in ('F02', 'F03'):
            return year_index + 0.5

        schedule = (payment_schedule or '').strip().upper()
        if schedule == '60 HARI TIAP TAHUN':
            return 300.0 / 360.0
        if schedule == 'TIAP BULAN':
            return 0.5
        return 1.0

    def _generate_logic_table_lines(self):
        line_model = self.env['logic.table']
        logic_records = self.env['rpc.hierarchy.logic'].search(
            [('active', '=', True)], order='sequence, id'
        )
        financial_codes = {'F01', 'F02', 'F03'}

        for document in self:
            line_model.search([('document_id', '=', document.id)]).unlink()
            if document.tahun_mulai_sewa <= 0 or document.masa_sewa <= 0:
                continue

            lease_year_count = math.ceil(document.masa_sewa / 12.0)
            credit_months = document.masa_kredit or document.masa_sewa
            credit_year_count = math.ceil(credit_months / 12.0)
            values_list = []

            for logic in logic_records:
                code = (logic.cost_group_code_id.name or '').strip().upper()
                year_count = (
                    credit_year_count if code in financial_codes
                    else lease_year_count
                )
                accum_unit_upper = accum_unit_lower = 0.0
                accum_total_upper = accum_total_lower = 0.0
                accum_gapping_upper = accum_gapping_lower = 0.0

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

                    gapping_factor = document._logic_gapping_factor(
                        code, logic.payment_schedule_id.name, year_index
                    )
                    gapping_upper = (
                        total_upper * document.cost_of_fund_pct * gapping_factor
                    )
                    gapping_lower = (
                        total_lower * document.cost_of_fund_pct * gapping_factor
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
                        'akumulasi_per_unit_batas_atas': accum_unit_upper,
                        'akumulasi_per_unit_batas_bawah': accum_unit_lower,
                        'total_year_batas_atas': total_upper,
                        'total_year_batas_bawah': total_lower,
                        'akumulasi_total_batas_atas': accum_total_upper,
                        'akumulasi_total_batas_bawah': accum_total_lower,
                        'gapping_total_year_batas_atas': gapping_upper,
                        'gapping_total_year_batas_bawah': gapping_lower,
                        'akumulasi_gapping_total_batas_atas': accum_gapping_upper,
                        'akumulasi_gapping_total_batas_bawah': accum_gapping_lower,
                    })

            if values_list:
                line_model.create(values_list)


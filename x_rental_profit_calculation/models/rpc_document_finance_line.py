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
    ('net_cashflow_upper', 'T2 - T3 - T4 (Batas Atas)'),
    ('net_cashflow_lower', 'T2 - T3 - T4 (Batas Bawah)'),
    ('rent_upper', 'sewa_per_bulan_batas_atas'),
    ('rent_lower', 'sewa_per_bulan_batas_bawah'),
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

    @api.depends('rate', 'document_id.otr_asuransi')
    def _compute_amount(self):
        for line in self:
            line.amount = line.rate * line.document_id.otr_asuransi


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

    def _evaluate_formula(self, formula):
        self.ensure_one()
        document = self.document_id
        if formula == 'total_downpayment_total':
            return document.total_downpayment * document.jumlah_unit
        if formula == 'cashback_total':
            return self._get_cashback_total()
        if formula == 'insurance_year_1_total':
            return self._get_insurance_year_1_total()
        if formula in ('net_cashflow_upper', 'net_cashflow_lower'):
            return self._get_cashback_total() - self._get_insurance_year_1_total()
        if formula == 'rent_upper':
            return document.sewa_per_bulan_batas_atas
        if formula == 'rent_lower':
            return document.sewa_per_bulan_batas_bawah
        return 0.0

    @api.depends(
        'finance_type_id.formula_batas_atas',
        'finance_type_id.formula_batas_bawah',
        'document_id.total_downpayment',
        'document_id.jumlah_unit',
        'document_id.cashback',
        'document_id.otr_leasing',
        'document_id.sewa_per_bulan_batas_atas',
        'document_id.sewa_per_bulan_batas_bawah',
        'document_id.purchase_line_ids.line_type',
        'document_id.purchase_line_ids.amount',
        'document_id.insurance_line_ids.tahun',
        'document_id.insurance_line_ids.sequence',
        'document_id.insurance_line_ids.rate',
    )
    def _compute_amounts(self):
        for line in self:
            line.batas_atas = line._evaluate_formula(
                line.finance_type_id.formula_batas_atas
            )
            line.batas_bawah = line._evaluate_formula(
                line.finance_type_id.formula_batas_bawah
            )

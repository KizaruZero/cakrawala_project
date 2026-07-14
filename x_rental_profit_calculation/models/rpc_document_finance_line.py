# -*- coding: utf-8 -*-
from odoo import api, fields, models


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


class RpcDocumentFinanceLine(models.Model):
    _name = 'rpc.document.finance.line'
    _description = 'RPC Finance Calculation Line'
    _order = 'document_id, table_type, sequence, id'

    document_id = fields.Many2one('rpc.document', string='RPC Document', required=True, ondelete='cascade')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='document_id.currency_id', store=True, readonly=True
    )
    table_type = fields.Selection([
        ('unit', 'Perhitungan / Unit'),
        ('cashflow', 'Cashflow'),
    ], string='Table Type', required=True, default='unit')
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Type', required=True)
    batas_atas = fields.Monetary(string='Batas Atas', currency_field='currency_id')
    batas_bawah = fields.Monetary(string='Batas Bawah', currency_field='currency_id')

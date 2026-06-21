# -*- coding: utf-8 -*-
from odoo import models, fields, api


class RpcDocumentPurchaseLine(models.Model):
    _name = 'rpc.document.purchase.line'
    _description = 'RPC Purchasing Line'
    _order = 'document_id, sequence, id'

    document_id = fields.Many2one('rpc.document', string='RPC Document', required=True, ondelete='cascade')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='document_id.currency_id', store=True, readonly=True
    )
    sequence = fields.Integer(string='Sequence', default=10)
    line_type = fields.Selection([
        ('harga_otr', 'Harga OTR'),
        ('discount', 'Discount'),
        ('cashback', 'Cashback'),
        ('special_req_1', 'Special Request 1'),
        ('special_req_2', 'Special Request 2'),
        ('special_req_3', 'Special Request 3'),
        ('special_req_4', 'Special Request 4'),
        ('special_req_5', 'Special Request 5'),
        ('biaya_ekspedisi', 'Biaya Ekspedisi/Pengiriman'),
    ], string='Line Type', required=True)
    description = fields.Char(string='Description', required=True)
    amount = fields.Monetary(string='Harga', currency_field='currency_id')
    capitalized = fields.Boolean(string='Dikapitalisasi')


class RpcDocumentDealerLine(models.Model):
    _name = 'rpc.document.dealer.line'
    _description = 'RPC Dealer Information Line'
    _order = 'document_id, sequence, id'

    document_id = fields.Many2one('rpc.document', string='RPC Document', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    no = fields.Integer(string='No', compute='_compute_no')
    description = fields.Char(string='Description', required=True)
    jumlah_unit = fields.Integer(string='Jumlah Unit')

    @api.depends('document_id.dealer_line_ids', 'sequence')
    def _compute_no(self):
        for document in self.mapped('document_id'):
            lines = document.dealer_line_ids.sorted(lambda line: (line.sequence, line.id))
            for index, line in enumerate(lines, start=1):
                line.no = index
        for line in self.filtered(lambda line: not line.document_id):
            line.no = 0

# -*- coding: utf-8 -*-
from odoo import models, fields, api


class RpcDocumentSpecialRequestLine(models.Model):
    _name = 'rpc.document.special.request.line'
    _description = 'RPC Special Request Kendaraan Line'
    _order = 'document_id, sequence'

    document_id = fields.Many2one('rpc.document', string='RPC Document', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    no = fields.Integer(string='No', compute='_compute_no')
    description = fields.Text(string='Description', required=True)

    @api.depends('document_id.special_request_ids', 'sequence')
    def _compute_no(self):
        for document in self.mapped('document_id'):
            lines = document.special_request_ids.sorted(lambda line: (line.sequence, line.id))
            for index, line in enumerate(lines, start=1):
                line.no = index
        for line in self.filtered(lambda line: not line.document_id):
            line.no = 0

# -*- coding: utf-8 -*-
from odoo import models, fields, api


class RpcDocumentStnkLine(models.Model):
    _name = 'rpc.document.stnk.line'
    _description = 'RPC Estimasi Biaya STNK Line'
    _order = 'document_id, sequence, tahun'

    document_id = fields.Many2one('rpc.document', string='RPC Document', required=True, ondelete='cascade')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='document_id.currency_id', store=True, readonly=True
    )
    sequence = fields.Integer(string='Sequence', default=10)
    tahun = fields.Integer(string='Tahun')
    rate = fields.Float(string='Rate (%)', digits=(5, 4))
    amount = fields.Monetary(
        string='Amount', compute='_compute_amount', store=True, currency_field='currency_id'
    )

    @api.depends('rate', 'document_id.otr_final')
    def _compute_amount(self):
        for line in self:
            # The percentage widget stores 1.8% as 0.018.
            line.amount = line.rate * line.document_id.otr_final

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if not self.env.context.get('rpc_skip_operational_year_sync'):
            lines.mapped('document_id')._sync_operational_line_years()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if (
            not self.env.context.get('rpc_skip_operational_year_sync')
            and {'document_id', 'sequence', 'tahun'}.intersection(vals)
        ):
            self.mapped('document_id')._sync_operational_line_years()
        return result


class RpcDocumentServiceLine(models.Model):
    _name = 'rpc.document.service.line'
    _description = 'RPC Estimasi Biaya Service Line'
    _order = 'document_id, sequence, tahun'

    document_id = fields.Many2one('rpc.document', string='RPC Document', required=True, ondelete='cascade')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='document_id.currency_id', store=True, readonly=True
    )
    sequence = fields.Integer(string='Sequence', default=10)
    tahun = fields.Integer(string='Tahun')
    rate = fields.Float(string='Rate (%)', digits=(5, 4))
    amount = fields.Monetary(
        string='Amount', compute='_compute_amount', store=True, currency_field='currency_id'
    )

    @api.depends('rate', 'document_id.otr_final')
    def _compute_amount(self):
        for line in self:
            # Keep the service calculation consistent with the STNK lines.
            line.amount = line.rate * line.document_id.otr_final

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if not self.env.context.get('rpc_skip_operational_year_sync'):
            lines.mapped('document_id')._sync_operational_line_years()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if (
            not self.env.context.get('rpc_skip_operational_year_sync')
            and {'document_id', 'sequence', 'tahun'}.intersection(vals)
        ):
            self.mapped('document_id')._sync_operational_line_years()
        return result

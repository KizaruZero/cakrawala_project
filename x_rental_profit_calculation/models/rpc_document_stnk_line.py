# -*- coding: utf-8 -*-
from odoo import models, fields, api


def _operational_year_label(year, start_year):
    """Display rental-year ordinals without replacing calendar-year keys."""
    if not year:
        return False
    if 1 <= year <= 5:
        number = year  # Legacy records stored rental-year numbers directly.
    elif start_year > 0 and year >= start_year:
        number = year - start_year + 1
    else:
        # Do not invent a rental year when the header is incomplete/invalid.
        return str(year)
    labels = ('Tahun Pertama', 'Tahun Kedua', 'Tahun Ketiga', 'Tahun Keempat', 'Tahun Kelima')
    return labels[number - 1] if number <= len(labels) else f'Tahun ke-{number}'


class RpcDocumentStnkLine(models.Model):
    _name = 'rpc.document.stnk.line'
    _description = 'RPC Estimasi Biaya STNK Line'
    _order = 'document_id, tahun, sequence, id'

    document_id = fields.Many2one('rpc.document', string='RPC Document', required=True, ondelete='cascade')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='document_id.currency_id', store=True, readonly=True
    )
    sequence = fields.Integer(string='Sequence', default=10)
    tahun = fields.Integer(string='Tahun')
    tahun_label = fields.Char(
        string='Tahun', compute='_compute_tahun_label',
        help='Urutan tahun sejak Tahun Mulai Sewa. Tahun kalender asli tetap digunakan untuk perhitungan.',
    )
    rate = fields.Float(string='Rate (%)', digits=(5, 4))
    amount = fields.Monetary(
        string='Amount', compute='_compute_amount', store=True, currency_field='currency_id'
    )

    @api.depends('tahun', 'document_id.tahun_mulai_sewa')
    def _compute_tahun_label(self):
        for line in self:
            line.tahun_label = _operational_year_label(line.tahun, line.document_id.tahun_mulai_sewa)

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
    _order = 'document_id, tahun, sequence, id'

    document_id = fields.Many2one('rpc.document', string='RPC Document', required=True, ondelete='cascade')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='document_id.currency_id', store=True, readonly=True
    )
    sequence = fields.Integer(string='Sequence', default=10)
    tahun = fields.Integer(string='Tahun')
    tahun_label = fields.Char(
        string='Tahun', compute='_compute_tahun_label',
        help='Urutan tahun sejak Tahun Mulai Sewa. Tahun kalender asli tetap digunakan untuk perhitungan.',
    )
    rate = fields.Float(string='Rate (%)', digits=(5, 4))
    amount = fields.Monetary(
        string='Amount', compute='_compute_amount', store=True, currency_field='currency_id'
    )

    @api.depends('tahun', 'document_id.tahun_mulai_sewa')
    def _compute_tahun_label(self):
        for line in self:
            line.tahun_label = _operational_year_label(line.tahun, line.document_id.tahun_mulai_sewa)

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

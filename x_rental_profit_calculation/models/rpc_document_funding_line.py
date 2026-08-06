# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RpcDocumentFundingLineMixin(models.AbstractModel):
    _name = 'rpc.document.funding.line.mixin'
    _description = 'RPC Document Funding Line Mixin'

    document_id = fields.Many2one(
        'rpc.document',
        string='RPC Document',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Urutan', default=10, readonly=True)
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='document_id.currency_id',
        store=True,
        readonly=True,
    )
    hierarchy_1_id = fields.Many2one(
        'rpc.funding.hierarchy.1',
        string='Hierarchy 1',
        required=True,
        ondelete='restrict',
        readonly=True,
    )
    hierarchy_2_id = fields.Many2one(
        'rpc.funding.hierarchy.2',
        string='Hierarchy 2',
        required=True,
        ondelete='restrict',
        domain="[('hierarchy_1_id', '=', hierarchy_1_id)]",
        readonly=True,
    )
    hierarchy_3_id = fields.Many2one(
        'rpc.funding.hierarchy.3',
        string='Hierarchy 3',
        required=True,
        ondelete='restrict',
        domain="[('hierarchy_2_id', '=', hierarchy_2_id)]",
        readonly=True,
    )
    tahun_1 = fields.Monetary(
        string='Tahun 1', currency_field='currency_id', readonly=True
    )
    tahun_2 = fields.Monetary(
        string='Tahun 2', currency_field='currency_id', readonly=True
    )
    tahun_3 = fields.Monetary(
        string='Tahun 3', currency_field='currency_id', readonly=True
    )
    tahun_4 = fields.Monetary(
        string='Tahun 4', currency_field='currency_id', readonly=True
    )
    tahun_5 = fields.Monetary(
        string='Tahun 5', currency_field='currency_id', readonly=True
    )

    @api.onchange('hierarchy_1_id')
    def _onchange_hierarchy_1_id(self):
        for line in self:
            if (
                line.hierarchy_2_id
                and line.hierarchy_2_id.hierarchy_1_id != line.hierarchy_1_id
            ):
                line.hierarchy_2_id = False
                line.hierarchy_3_id = False

    @api.onchange('hierarchy_2_id')
    def _onchange_hierarchy_2_id(self):
        for line in self:
            if line.hierarchy_2_id:
                line.hierarchy_1_id = line.hierarchy_2_id.hierarchy_1_id
            if (
                line.hierarchy_3_id
                and line.hierarchy_3_id.hierarchy_2_id != line.hierarchy_2_id
            ):
                line.hierarchy_3_id = False

    @api.onchange('hierarchy_3_id')
    def _onchange_hierarchy_3_id(self):
        for line in self:
            if line.hierarchy_3_id:
                line.hierarchy_2_id = line.hierarchy_3_id.hierarchy_2_id
                line.hierarchy_1_id = line.hierarchy_2_id.hierarchy_1_id

    @api.constrains('hierarchy_1_id', 'hierarchy_2_id', 'hierarchy_3_id')
    def _check_hierarchy_consistency(self):
        for line in self:
            if line.hierarchy_2_id.hierarchy_1_id != line.hierarchy_1_id:
                raise ValidationError(
                    _('Hierarchy 2 harus merupakan turunan dari Hierarchy 1 yang dipilih!')
                )
            if line.hierarchy_3_id.hierarchy_2_id != line.hierarchy_2_id:
                raise ValidationError(
                    _('Hierarchy 3 harus merupakan turunan dari Hierarchy 2 yang dipilih!')
                )


class RpcDocumentFundingNeedsBatasAtas(models.Model):
    _name = 'rpc.document.funding.needs.batas.atas'
    _description = 'RPC Funding Needs Batas Atas'
    _inherit = 'rpc.document.funding.line.mixin'
    _table = 'funding_needs_batas_atas'
    _order = 'document_id, sequence, id'


class RpcDocumentGappingCostBatasAtas(models.Model):
    _name = 'rpc.document.gapping.cost.batas.atas'
    _description = 'RPC Gapping Cost Batas Atas'
    _inherit = 'rpc.document.funding.line.mixin'
    _table = 'gapping_cost_batas_atas'
    _order = 'document_id, sequence, id'


class RpcDocumentFundingNeedsBatasBawah(models.Model):
    _name = 'rpc.document.funding.needs.batas.bawah'
    _description = 'RPC Funding Needs Batas Bawah'
    _inherit = 'rpc.document.funding.line.mixin'
    _table = 'funding_needs_batas_bawah'
    _order = 'document_id, sequence, id'


class RpcDocumentGappingCostBatasBawah(models.Model):
    _name = 'rpc.document.gapping.cost.batas.bawah'
    _description = 'RPC Gapping Cost Batas Bawah'
    _inherit = 'rpc.document.funding.line.mixin'
    _table = 'gapping_cost_batas_bawah'
    _order = 'document_id, sequence, id'

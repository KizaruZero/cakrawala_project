# -*- coding: utf-8 -*-
from odoo import fields, models


class RpcFundingHierarchy1(models.Model):
    _name = 'rpc.funding.hierarchy.1'
    _description = 'RPC Funding Hierarchy 1'
    _order = 'sequence, name, id'

    name = fields.Char(string='Hierarchy 1', required=True)
    code = fields.Char(string='Kode')
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    hierarchy_2_ids = fields.One2many(
        'rpc.funding.hierarchy.2', 'hierarchy_1_id', string='Hierarchy 2'
    )

    _name_unique = models.Constraint(
        'UNIQUE(name)',
        'Nama Hierarchy 1 harus unik!',
    )


class RpcFundingHierarchy2(models.Model):
    _name = 'rpc.funding.hierarchy.2'
    _description = 'RPC Funding Hierarchy 2'
    _order = 'hierarchy_1_id, sequence, name, id'

    name = fields.Char(string='Hierarchy 2', required=True)
    code = fields.Char(string='Kode')
    hierarchy_1_id = fields.Many2one(
        'rpc.funding.hierarchy.1',
        string='Hierarchy 1',
        required=True,
        ondelete='restrict',
        index=True,
    )
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    hierarchy_3_ids = fields.One2many(
        'rpc.funding.hierarchy.3', 'hierarchy_2_id', string='Hierarchy 3'
    )

    _name_hierarchy_1_unique = models.Constraint(
        'UNIQUE(hierarchy_1_id, name)',
        'Nama Hierarchy 2 harus unik pada setiap Hierarchy 1!',
    )


class RpcFundingHierarchy3(models.Model):
    _name = 'rpc.funding.hierarchy.3'
    _description = 'RPC Funding Hierarchy 3'
    _order = 'hierarchy_2_id, sequence, name, id'

    name = fields.Char(string='Hierarchy 3', required=True)
    code = fields.Char(string='Kode')
    hierarchy_2_id = fields.Many2one(
        'rpc.funding.hierarchy.2',
        string='Hierarchy 2',
        required=True,
        ondelete='restrict',
        index=True,
    )
    hierarchy_1_id = fields.Many2one(
        'rpc.funding.hierarchy.1',
        string='Hierarchy 1',
        related='hierarchy_2_id.hierarchy_1_id',
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)

    _name_hierarchy_2_unique = models.Constraint(
        'UNIQUE(hierarchy_2_id, name)',
        'Nama Hierarchy 3 harus unik pada setiap Hierarchy 2!',
    )

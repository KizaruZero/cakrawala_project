# -*- coding: utf-8 -*-
from odoo import fields, models


class RpcHierarchyLogicHierarchy(models.Model):
    _name = 'rpc.hierarchy.logic.hierarchy'
    _description = 'RPC Hierarchy Logic Hierarchy Master'
    _order = 'sequence, name, id'

    name = fields.Char(string='Hierarchy', required=True)
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    logic_ids = fields.One2many(
        'rpc.hierarchy.logic', 'hierarchy_id', string='Hierarchy Logic Table'
    )

    _name_unique = models.Constraint(
        'UNIQUE(name)',
        'Nama Hierarchy harus unik!',
    )


class RpcHierarchyLogicCostGroupCode(models.Model):
    _name = 'rpc.hierarchy.logic.cost.group.code'
    _description = 'RPC Hierarchy Logic Cost Group Code Master'
    _order = 'sequence, name, id'

    name = fields.Char(string='Cost Group Code', required=True)
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    logic_ids = fields.One2many(
        'rpc.hierarchy.logic', 'cost_group_code_id',
        string='Hierarchy Logic Table',
    )

    _name_unique = models.Constraint(
        'UNIQUE(name)',
        'Cost Group Code harus unik!',
    )


class RpcHierarchyLogicCostGroupName(models.Model):
    _name = 'rpc.hierarchy.logic.cost.group.name'
    _description = 'RPC Hierarchy Logic Cost Group Name Master'
    _order = 'sequence, name, id'

    name = fields.Char(string='Cost Group Name', required=True)
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    logic_ids = fields.One2many(
        'rpc.hierarchy.logic', 'cost_group_name_id',
        string='Hierarchy Logic Table',
    )

    _name_unique = models.Constraint(
        'UNIQUE(name)',
        'Cost Group Name harus unik!',
    )


class RpcHierarchyLogicPaymentSchedule(models.Model):
    _name = 'rpc.hierarchy.logic.payment.schedule'
    _description = 'RPC Hierarchy Logic Payment Schedule Master'
    _order = 'sequence, name, id'

    name = fields.Char(string='Jadwal Pembayaran', required=True)
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    logic_ids = fields.One2many(
        'rpc.hierarchy.logic', 'payment_schedule_id',
        string='Hierarchy Logic Table',
    )

    _name_unique = models.Constraint(
        'UNIQUE(name)',
        'Jadwal Pembayaran harus unik!',
    )


class RpcHierarchyLogic(models.Model):
    _name = 'rpc.hierarchy.logic'
    _description = 'RPC Hierarchy Logic Table'
    _order = 'sequence, id'
    _rec_name = 'cost_group_code_id'

    sequence = fields.Integer(string='Urutan', default=10)
    hierarchy_id = fields.Many2one(
        'rpc.hierarchy.logic.hierarchy',
        string='Hierarchy',
        required=True,
        ondelete='restrict',
        index=True,
    )
    cost_group_code_id = fields.Many2one(
        'rpc.hierarchy.logic.cost.group.code',
        string='Cost Group Code',
        required=True,
        ondelete='restrict',
        index=True,
    )
    cost_group_name_id = fields.Many2one(
        'rpc.hierarchy.logic.cost.group.name',
        string='Cost Group Name',
        required=True,
        ondelete='restrict',
        index=True,
    )
    payment_schedule_id = fields.Many2one(
        'rpc.hierarchy.logic.payment.schedule',
        string='Jadwal Pembayaran',
        required=True,
        ondelete='restrict',
        index=True,
    )
    formula = fields.Char(string='Formula')
    active = fields.Boolean(string='Aktif', default=True)

    _cost_group_code_unique = models.Constraint(
        'UNIQUE(cost_group_code_id)',
        'Cost Group Code hanya boleh digunakan satu kali pada Hierarchy Logic Table!',
    )

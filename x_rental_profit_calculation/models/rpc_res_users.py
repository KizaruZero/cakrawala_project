# -*- coding: utf-8 -*-
from odoo import Command, api, fields, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    is_rpc_role = fields.Boolean(
        string='RPC Role',
        help='Menandai group yang dapat dipilih sebagai role RPC pada user.',
    )


class ResUsers(models.Model):
    _inherit = 'res.users'

    rpc_role_ids = fields.Many2many(
        'res.groups',
        string='RPC Roles',
        compute='_compute_rpc_role_ids',
        inverse='_inverse_rpc_role_ids',
        domain=[('is_rpc_role', '=', True)],
        help='Satu user dapat memiliki lebih dari satu role RPC.',
    )

    @api.depends('group_ids')
    def _compute_rpc_role_ids(self):
        rpc_roles = self.env['res.groups'].search([('is_rpc_role', '=', True)])
        for user in self:
            user.rpc_role_ids = user.group_ids & rpc_roles

    def _inverse_rpc_role_ids(self):
        rpc_roles = self.env['res.groups'].search([('is_rpc_role', '=', True)])
        for user in self:
            non_rpc_groups = user.group_ids - rpc_roles
            user.group_ids = [Command.set((non_rpc_groups | user.rpc_role_ids).ids)]

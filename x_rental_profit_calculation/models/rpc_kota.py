# -*- coding: utf-8 -*-
from odoo import models, fields


class RpcKota(models.Model):
    _name = 'rpc.kota'
    _description = 'RPC Kota Master'
    _order = 'provinsi_id, name'

    name = fields.Char(string='Kota', required=True)
    provinsi_id = fields.Many2one('rpc.provinsi', string='Provinsi', required=True, ondelete='cascade')
    active = fields.Boolean(string='Aktif', default=True)

# -*- coding: utf-8 -*-
from odoo import models, fields


class RpcWilayah(models.Model):
    _name = 'rpc.wilayah'
    _description = 'RPC Wilayah Master'
    _order = 'name'

    name = fields.Char(string='Wilayah', required=True)
    code = fields.Char(string='Kode')
    active = fields.Boolean(string='Aktif', default=True)
    provinsi_ids = fields.One2many('rpc.provinsi', 'wilayah_id', string='Provinsi')

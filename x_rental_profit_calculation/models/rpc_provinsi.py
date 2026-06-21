# -*- coding: utf-8 -*-
from odoo import models, fields


class RpcProvinsi(models.Model):
    _name = 'rpc.provinsi'
    _description = 'RPC Provinsi Master'
    _order = 'name'

    name = fields.Char(string='Provinsi', required=True)
    wilayah_id = fields.Many2one('rpc.wilayah', string='Wilayah', required=True, ondelete='restrict')
    active = fields.Boolean(string='Aktif', default=True)
    kota_ids = fields.One2many('rpc.kota', 'provinsi_id', string='Kota')

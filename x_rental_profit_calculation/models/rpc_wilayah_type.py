# -*- coding: utf-8 -*-
from odoo import fields, models


class RpcWilayahType(models.Model):
    _name = 'rpc.wilayah.type'
    _description = 'RPC Wilayah Type'
    _order = 'sequence, name, id'

    name = fields.Char(string='Wilayah Type', required=True)
    code = fields.Char(string='Kode', required=True)
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    asuransi_rate_ids = fields.One2many(
        'rpc.asuransi.rate',
        'wilayah_type_id',
        string='Mapping Kategori OTR dan Rate',
    )

    _name_unique = models.Constraint(
        'UNIQUE(name)',
        'Nama Wilayah Type harus unik!',
    )
    _code_unique = models.Constraint(
        'UNIQUE(code)',
        'Kode Wilayah Type harus unik!',
    )

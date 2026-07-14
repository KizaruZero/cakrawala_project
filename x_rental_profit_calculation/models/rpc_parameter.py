# -*- coding: utf-8 -*-
from odoo import models, fields, api


class RpcParameter(models.Model):
    _name = 'rpc.parameter'
    _description = 'RPC Parameter Master'
    _order = 'parameter_type, sequence, name'

    name = fields.Char(string='Nama', required=True)
    code = fields.Char(string='Kode')
    parameter_type = fields.Selection([
        ('type_of_klien', 'Type of Klien'),
        ('jenis_transaksi', 'Jenis Transaksi'),
        ('tujuan', 'Tujuan'),
        ('sumber', 'Sumber'),
        ('sumber_daya', 'Sumber Daya'),
        ('jenis_kendaraan', 'Jenis Kendaraan'),
        ('penggunaan_kendaraan', 'Penggunaan Kendaraan'),
        ('pemakaian', 'Pemakaian'),
        ('merek', 'Merek'),
        ('leasing_bank', 'Leasing/Bank'),
        ('jenis_angsuran', 'Jenis Angsuran'),
        ('wilayah_type', 'Wilayah Type'),
    ], string='Tipe Parameter', required=True)
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    note = fields.Text(string='Catatan')

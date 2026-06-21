# -*- coding: utf-8 -*-
from odoo import models, fields, api


class RpcKendaraanKategori(models.Model):
    _name = 'rpc.kendaraan.kategori'
    _description = 'RPC Kendaraan Kategori OTR Mapping'
    _order = 'jenis_kendaraan, otr_from'

    name = fields.Char(string='Nama Kategori', required=True)
    jenis_kendaraan = fields.Selection([
        ('non_bus_non_truk', 'Non-Bus & Non-Truk'),
        ('truk_pickup', 'Truk & Pick-Up'),
        ('bus', 'Bus'),
        ('roda_2', 'Roda 2'),
    ], string='Jenis Kendaraan', required=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        required=True, default=lambda self: self.env.company.currency_id
    )
    otr_from = fields.Monetary(string='OTR Leasing Dari', currency_field='currency_id')
    otr_to = fields.Monetary(string='OTR Leasing Sampai', currency_field='currency_id')
    group_otr = fields.Char(string='Group OTR', required=True)
    active = fields.Boolean(string='Aktif', default=True)


class RpcAsuransiRate(models.Model):
    _name = 'rpc.asuransi.rate'
    _description = 'RPC Asuransi Rate'
    _order = 'wilayah_id, kategori_id, wilayah_type'

    wilayah_id = fields.Many2one('rpc.wilayah', string='Wilayah', required=True, ondelete='restrict')
    kategori_id = fields.Many2one('rpc.kendaraan.kategori', string='Kategori Kendaraan', required=True, ondelete='restrict')
    wilayah_type = fields.Selection([
        ('batas_atas', 'Batas Atas'),
        ('batas_bawah', 'Batas Bawah'),
        ('crs', 'CRS'),
    ], string='Wilayah Type', required=True)
    rate = fields.Float(string='Rate (%)', digits=(5, 4))
    active = fields.Boolean(string='Aktif', default=True)

    _sql_constraints = [
        ('unique_rate', 'UNIQUE(wilayah_id, kategori_id, wilayah_type)',
         'Rate untuk kombinasi Wilayah, Kategori, dan Type sudah ada!')
    ]

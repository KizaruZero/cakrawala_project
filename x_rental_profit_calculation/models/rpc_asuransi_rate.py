# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RpcKendaraanKategori(models.Model):
    _name = 'rpc.kendaraan.kategori'
    _description = 'RPC Kendaraan Kategori OTR Mapping'
    _order = 'jenis_kendaraan_id, otr_from'

    name = fields.Char(string='Nama Kategori', required=True)
    jenis_kendaraan_id = fields.Many2one(
        'rpc.parameter',
        string='Jenis Kendaraan',
        domain=[('parameter_type', '=', 'jenis_kendaraan')],
        ondelete='restrict',
        index=True,
    )
    # Transitional field for databases that still store the old selection value.
    # It can be removed after every database has migrated to jenis_kendaraan_id.
    jenis_kendaraan = fields.Char(string='Jenis Kendaraan (Legacy)', copy=False)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        required=True, default=lambda self: self.env.company.currency_id
    )
    otr_from = fields.Monetary(string='OTR Leasing Dari', currency_field='currency_id')
    otr_to = fields.Monetary(string='OTR Leasing Sampai', currency_field='currency_id')
    group_otr = fields.Char(string='Group OTR', required=True)
    active = fields.Boolean(string='Aktif', default=True)
    asuransi_rate_ids = fields.One2many(
        'rpc.asuransi.rate',
        'kategori_id',
        string='Mapping Asuransi Type dan Rate',
    )

    @api.model
    def _find_jenis_kendaraan(self, code):
        return self.env['rpc.parameter'].search([
            ('parameter_type', '=', 'jenis_kendaraan'),
            ('code', '=', code),
        ], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            jenis_kendaraan_id = vals.get('jenis_kendaraan_id')
            legacy_code = vals.get('jenis_kendaraan')
            if jenis_kendaraan_id:
                parameter = self.env['rpc.parameter'].browse(jenis_kendaraan_id)
                if parameter.parameter_type != 'jenis_kendaraan':
                    raise ValidationError(_(
                        'Parameter Jenis Kendaraan harus memiliki Tipe Parameter Jenis Kendaraan!'
                    ))
                vals['jenis_kendaraan'] = parameter.code
            elif legacy_code:
                parameter = self._find_jenis_kendaraan(legacy_code)
                if parameter:
                    vals['jenis_kendaraan_id'] = parameter.id
            if not vals.get('jenis_kendaraan_id'):
                raise ValidationError(_('Jenis Kendaraan wajib diisi!'))
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if 'jenis_kendaraan_id' in vals:
            if not vals['jenis_kendaraan_id']:
                raise ValidationError(_('Jenis Kendaraan wajib diisi!'))
            parameter = self.env['rpc.parameter'].browse(vals['jenis_kendaraan_id'])
            if parameter.parameter_type != 'jenis_kendaraan':
                raise ValidationError(_(
                    'Parameter Jenis Kendaraan harus memiliki Tipe Parameter Jenis Kendaraan!'
                ))
            vals['jenis_kendaraan'] = parameter.code
        elif 'jenis_kendaraan' in vals:
            parameter = self._find_jenis_kendaraan(vals['jenis_kendaraan'])
            if not parameter:
                raise ValidationError(_('Kode Jenis Kendaraan tidak ditemukan!'))
            vals['jenis_kendaraan_id'] = parameter.id
        return super().write(vals)

    @api.constrains('jenis_kendaraan_id')
    def _check_jenis_kendaraan_parameter_type(self):
        for rec in self:
            if (
                rec.jenis_kendaraan_id
                and rec.jenis_kendaraan_id.parameter_type != 'jenis_kendaraan'
            ):
                raise ValidationError(_(
                    'Parameter Jenis Kendaraan harus memiliki Tipe Parameter Jenis Kendaraan!'
                ))


class RpcAsuransiRate(models.Model):
    _name = 'rpc.asuransi.rate'
    _description = 'RPC Asuransi Rate'
    _order = 'wilayah_id, kategori_id, wilayah_type_id'

    wilayah_id = fields.Many2one('rpc.wilayah', string='Wilayah', required=True, ondelete='restrict')
    kategori_id = fields.Many2one('rpc.kendaraan.kategori', string='Kategori Kendaraan', required=True, ondelete='restrict')
    wilayah_type_id = fields.Many2one(
        'rpc.wilayah.type',
        string='Asuransi Type',
        ondelete='restrict',
        index=True,
        help='Master Asuransi Type yang dipakai pada mapping rate kategori OTR.',
    )
    # Transitional field for databases that still store the old selection value.
    # It can be removed after every database has migrated to wilayah_type_id.
    wilayah_type = fields.Char(string='Wilayah Type (Legacy)', copy=False)
    rate = fields.Float(string='Rate (%)', digits=(5, 4))
    active = fields.Boolean(string='Aktif', default=True)

    _unique_rate = models.Constraint(
        'UNIQUE(wilayah_id, kategori_id, wilayah_type_id)',
        'Rate untuk kombinasi Wilayah, Kategori, dan Type sudah ada!',
    )

    @api.model
    def _find_wilayah_type(self, code):
        return self.env['rpc.wilayah.type'].search([('code', '=', code)], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            wilayah_type_id = vals.get('wilayah_type_id')
            legacy_code = vals.get('wilayah_type')
            if wilayah_type_id:
                vals['wilayah_type'] = self.env['rpc.wilayah.type'].browse(
                    wilayah_type_id
                ).code
            elif legacy_code:
                wilayah_type = self._find_wilayah_type(legacy_code)
                if wilayah_type:
                    vals['wilayah_type_id'] = wilayah_type.id
            if not vals.get('wilayah_type_id'):
                raise ValidationError(_('Wilayah Type wajib diisi!'))
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if 'wilayah_type_id' in vals:
            if not vals['wilayah_type_id']:
                raise ValidationError(_('Wilayah Type wajib diisi!'))
            vals['wilayah_type'] = self.env['rpc.wilayah.type'].browse(
                vals['wilayah_type_id']
            ).code
        elif 'wilayah_type' in vals:
            wilayah_type = self._find_wilayah_type(vals['wilayah_type'])
            if not wilayah_type:
                raise ValidationError(_('Kode Wilayah Type tidak ditemukan!'))
            vals['wilayah_type_id'] = wilayah_type.id
        return super().write(vals)

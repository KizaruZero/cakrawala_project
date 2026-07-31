from odoo import models, fields, api

class CrmClientType(models.Model):
    _name = 'crm.client.type'
    _description = 'CRM Client Type'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(default=True)

class CrmTujuan(models.Model):
    _name = 'crm.tujuan'
    _description = 'CRM Tujuan'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(default=True)

class CrmJenisTransaksi(models.Model):
    _name = 'crm.jenis.transaksi'
    _description = 'CRM Jenis Transaksi'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.name:
                existing = self.env['rpc.parameter'].search([
                    ('parameter_type', '=', 'jenis_transaksi'),
                    ('name', '=ilike', rec.name)
                ], limit=1)
                if not existing:
                    self.env['rpc.parameter'].create({
                        'parameter_type': 'jenis_transaksi',
                        'name': rec.name
                    })
        return records

class CrmSourceCustom(models.Model):
    _name = 'crm.source.custom'
    _description = 'CRM Source'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(default=True)

class CrmJenisKendaraan(models.Model):
    _name = 'crm.jenis.kendaraan'
    _description = 'CRM Jenis Kendaraan'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(default=True)

class CrmSumberDaya(models.Model):
    _name = 'crm.sumber.daya'
    _description = 'CRM Sumber Daya'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(default=True)

class CrmPenggunaanKendaraan(models.Model):
    _name = 'crm.penggunaan.kendaraan'
    _description = 'CRM Penggunaan Kendaraan'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(default=True)

class CrmRentalType(models.Model):
    _name = 'crm.rental.type'
    _description = 'CRM Rental Type'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(default=True)

class CrmUsageLocation(models.Model):
    _name = 'crm.usage.location'
    _description = 'CRM Usage Location'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(default=True)

class CrmPemakaian(models.Model):
    _name = 'crm.pemakaian'
    _description = 'Pemakaian Master Data'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(default=True)

from odoo import models, fields, api
from datetime import date
from odoo.exceptions import ValidationError
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _default_x_contact_type(self):
        return 'company' if self.env.context.get('default_is_company') else 'person'

    x_contact_type = fields.Selection([
        ('person', 'Person'),
        ('company', 'Company')
    ], string="Tipe Kontak", default=_default_x_contact_type, required=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'x_contact_type' in vals:
                vals['is_company'] = (vals['x_contact_type'] == 'company')
                vals['company_type'] = vals['x_contact_type']
            else:
                is_comp = vals.get('is_company', self.env.context.get('default_is_company', False))
                vals['x_contact_type'] = 'company' if is_comp else 'person'
        return super(ResPartner, self).create(vals_list)

    def write(self, vals):
        if 'x_contact_type' in vals:
            vals['is_company'] = (vals['x_contact_type'] == 'company')
            vals['company_type'] = vals['x_contact_type']
        return super(ResPartner, self).write(vals)

    @api.onchange('x_contact_type')
    def _onchange_x_contact_type(self):
        for rec in self:
            if rec.x_contact_type == 'company':
                rec.is_company = True
                rec.company_type = 'company'
            else:
                rec.is_company = False
                rec.company_type = 'person'

    # PKS Information
    is_pks = fields.Boolean(string="Is PKS?")
    pks_valid_from = fields.Date(string="Valid From")
    pks_valid_until = fields.Date(string="Valid Until")

    # Partner Role
    partner_role = fields.Selection([
        ('customer', 'Customer'),
        ('vendor', 'Vendor'),
        ('contact', 'Contact')
    ], string="Partner Role", required=True, default='contact')

    # Company Information Fields
    bidang_usaha = fields.Text(
        string='Bidang Usaha',
        help='Bidang usaha perusahaan'
    )
    kepemilikan = fields.Text(
        string='Kepemilikan',
        help='Status kepemilikan perusahaan'
    )
    pemegang_saham = fields.Text(
        string='Pemegang Saham',
        help='Informasi pemegang saham'
    )
    group_perusahaan = fields.Text(
        string='Group Perusahaan',
        help='Grup perusahaan induk'
    )
    ukuran_perusahaan = fields.Text(
        string='Ukuran Perusahaan',
        help='Ukuran/skala perusahaan'
    )
    catatan_tambahan = fields.Text(
        string='Deskripsi / Catatan / Informasi Tambahan',
        help='Informasi tambahan tentang perusahaan'
    )
    jumlah_karyawan = fields.Char(
        string='Jumlah Karyawan',
        help='Total jumlah karyawan'
    )
    jumlah_populasi_fleet = fields.Char(
        string='Jumlah Populasi Fleet',
        help='Jumlah populasi armada kendaraan'
    )
    perusahaan_rental_saat_ini = fields.Text(
        string='Perusahaan Rental saat ini',
        help='Nama perusahaan rental saat ini'
    )
    tujuan_pemakaian = fields.Text(
        string='Tujuan Pemakaian',
        help='Tujuan penggunaan layanan'
    )

    @api.constrains('jumlah_karyawan', 'jumlah_populasi_fleet')
    def _check_numeric_fields(self):
        for rec in self:
            if rec.jumlah_karyawan and not rec.jumlah_karyawan.isdigit():
                raise ValidationError("Field 'Jumlah Karyawan' hanya boleh berisi angka.")
            if rec.jumlah_populasi_fleet and not rec.jumlah_populasi_fleet.isdigit():
                raise ValidationError("Field 'Jumlah Populasi Fleet' hanya boleh berisi angka.")

    @api.constrains('x_contact_type', 'child_ids')
    def _check_company_contact(self):
        import logging
        _logger = logging.getLogger(__name__)
        for partner in self:
            _logger.info(f"CHECK_COMPANY_CONTACT: name={partner.name}, x_contact_type={partner.x_contact_type}, child_ids={len(partner.child_ids)}")
            if partner.x_contact_type == 'company' and not partner.child_ids:
                raise ValidationError("Jika tipe kontak adalah Company (Perusahaan), Anda harus menambahkan minimal 1 Contact Person di tab 'Contacts & Addresses'!")



    akte_pendirian_attachment = fields.Binary(
        string='Akte Pendirian & Terakhir Perusahaan',
        help='Dokumen akte pendirian and perubahan terakhir perusahaan'
    )
    rekening_koran_attachment = fields.Binary(
        string='Rekening Koran 3 Bulan Terakhir',
        help='Laporan rekening koran 3 bulan terakhir'
    )
    lapkeu_audited_attachment = fields.Binary(
        string='Lapkeu Audited Tahunan Terakhir',
        help='Laporan keuangan audited tahun terakhir'
    )
    ktp_pengurus_attachment = fields.Binary(
        string='KTP/KIMS/Passport Pengurus Perusahaan',
        help='Dokumen identitas pengurus perusahaan'
    )
    domisili_attachment = fields.Binary(
        string='Domisili',
        help='Bukti domisili perusahaan'
    )
    nib_attachment = fields.Binary(
        string='NIB',
        help='Nomor Induk Berusaha'
    )
    npwp_attachment = fields.Binary(
        string='NPWP',
        help='Nomor Pokok Wajib Pajak'
    )
    surat_kuasa_attachment = fields.Binary(
        string='Surat Kuasa Penandatanganan',
        help='Surat kuasa penandatanganan dokumen'
    )
    slik_perusahaan_attachment = fields.Binary(
        string='SLIK (Perusahaan)',
        help='Laporan Sistem Informasi Layanan Informasi Keuangan'
    )

    ktp_individu_attachment = fields.Binary(
        string='KTP/KIMS/Passport',
        help='Dokumen identitas individu'
    )
    kartu_keluarga_attachment = fields.Binary(
        string='Kartu Keluarga WNI',
        help='Kartu keluarga WNI'
    )
    sim_attachment = fields.Binary(
        string='SIM yang masih berlaku',
        help='Surat izin mengemudi yang masih berlaku'
    )
    referensi_perusahaan_attachment = fields.Binary(
        string='Referensi Perusahaan',
        help='Surat referensi dari perusahaan'
    )
    surat_permintaan_attachment = fields.Binary(
        string='Surat permintaan sewa/konfirmasi',
        help='Surat permintaan/konfirmasi pembiayaan kendaraan'
    )
    rekening_3bulan_attachment = fields.Binary(
        string='Rekening 3 bulan terakhir',
        help='Laporan rekening 3 bulan terakhir'
    )
    slik_individu_attachment = fields.Binary(
        string='SLIK (Individu)',
        help='Laporan Sistem Informasi Layanan Informasi Keuangan individu'
    )
    dokumen_lainnya_attachment = fields.Binary(
        string='Lainnya',
        help='Dokumen pendukung lainnya'
    )

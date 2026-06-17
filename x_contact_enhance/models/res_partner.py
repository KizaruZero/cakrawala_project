from odoo import models, fields, api
from odoo.exceptions import ValidationError
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

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

import base64
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from odoo import fields, models
from odoo.tools.image import image_data_uri

FLEET_TERMS_TEMPLATE = (
    '<p><strong>Syarat-Syarat Kelengkapan Penagihan ke PT. CAKRAWALA RENTALINDO SEJAHTERA</strong></p>'
    '<ol>'
    '<li>Kwitansi BERMATERAI</li>'
    '<li>SPT (Surat Permohonan Transfer) - Lengkap dengan Nomor Rekening</li>'
    '<li>Faktur Pajak</li>'
    '<li>Esek-Esek Nomor Rangka</li>'
    '<li>Copy STNK</li>'
    '<li>Copy PO</li>'
    '<li>Copy SPK</li>'
    '<li>Copy Berita Serah Terima Kendaraan</li>'
    '<li>Print out foto mobil tampak depan</li>'
    '<li>Surat pernyataan BPKB / Cover Note Khusus area JABOTABEK</li>'
    '</ol>'
)


class ResCompany(models.Model):
    _inherit = 'res.company'

    po_contact_up = fields.Char(string='UP')
    po_contact_mobile = fields.Char(string='No. HP')
    po_sign = fields.Char(string='PO Sign')
    purchase_fleet_terms = fields.Html(
        string='Default Syarat dan Ketentuan (Fleet)', default=FLEET_TERMS_TEMPLATE,
        help='Default Syarat dan Ketentuan pada Rental Order, serta Detail Description PR dan PO '
             'berisi produk Fleet yang tidak dibuat dari Rental Order.',
    )

    def po_report_logo_data_uri(self):
        self.ensure_one()
        if not self.logo:
            return ''

        try:
            image = Image.open(BytesIO(base64.b64decode(self.logo)))
        except (OSError, UnidentifiedImageError):
            return image_data_uri(self.logo)
        if image.mode not in ('RGBA', 'LA'):
            return image_data_uri(self.logo)

        alpha = image.getchannel('A')
        bounds = alpha.point(lambda value: 255 if value > 10 else 0).getbbox()
        if not bounds:
            return image_data_uri(self.logo)

        image = image.crop(bounds)
        output = BytesIO()
        image.save(output, format='PNG')
        return 'data:image/png;base64,%s' % base64.b64encode(output.getvalue()).decode('ascii')

import base64
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from odoo import api, fields, models
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
    po_contact_id = fields.Many2one(
        'res.partner', string='UP', check_company=True,
        domain="[('is_company', '=', False), ('company_id', 'in', [False, id])]",
        help='Default Contact UP untuk Purchase Order baru perusahaan ini.',
    )
    po_contact_mobile = fields.Char(string='No. HP')
    po_sign = fields.Char(string='PO Sign')
    purchase_fleet_terms = fields.Html(
        string='Syarat dan Ketentuan Rental Order', default=FLEET_TERMS_TEMPLATE,
        help='Diisi ke Detail Description PR dan Terms and Conditions PO yang dibuat dari Rental Order, '
             'lalu ikut ke PO dari PR tersebut. Tidak ikut ke Bill.',
    )

    @api.constrains('po_contact_id')
    def _check_po_contact_company(self):
        self._check_company(['po_contact_id'])

    @api.onchange('po_contact_id')
    def _onchange_po_contact_id(self):
        for company in self:
            company.po_contact_mobile = (getattr(company.po_contact_id, 'mobile', False)
                                         or company.po_contact_id.phone or False)

    @api.model_create_multi
    def create(self, values_list):
        prepared = []
        for values in values_list:
            values = dict(values)
            if 'po_contact_id' in values and 'po_contact_mobile' not in values:
                contact = self.env['res.partner'].browse(values['po_contact_id']).exists()
                values['po_contact_mobile'] = getattr(contact, 'mobile', False) or contact.phone or False
            prepared.append(values)
        return super().create(prepared)

    def write(self, values):
        if 'po_contact_id' in values and 'po_contact_mobile' not in values:
            contact = self.env['res.partner'].browse(values['po_contact_id']).exists()
            values = {**values, 'po_contact_mobile': getattr(contact, 'mobile', False) or contact.phone or False}
        return super().write(values)
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

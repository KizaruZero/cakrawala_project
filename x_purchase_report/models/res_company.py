import base64
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from odoo import fields, models
from odoo.tools.image import image_data_uri


class ResCompany(models.Model):
    _inherit = 'res.company'

    po_contact_up = fields.Char(string='UP')
    po_contact_mobile = fields.Char(string='No. HP')
    po_sign = fields.Char(string='PO Sign')

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

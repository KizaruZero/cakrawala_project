import base64
from io import BytesIO

from PIL import Image, ImageChops

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    rental_invoice_stamp_product_id = fields.Many2one(
        'product.product', string='Rental Invoice Stamp Duty Product',
        check_company=True,
        domain="[('type', '=', 'service'), ('sale_ok', '=', True), ('company_id', 'in', [False, id])]",
        help='When configured, each new Billing Engine invoice includes IDR 10,000 '
             'stamp duty using this product income account and customer taxes. '
             'Existing draft/posted invoices are never charged retroactively.',
    )

    def _rental_report_logo(self):
        """Remove empty raster margins without modifying the saved company logo."""
        self.ensure_one()
        if not self.logo:
            return False

        try:
            logo = Image.open(BytesIO(base64.b64decode(self.logo)))
            logo.load()
            rgba = logo.convert('RGBA')
            alpha = rgba.getchannel('A')
            alpha_bounds = alpha.point(
                lambda value: 255 if value > 12 else 0
            ).getbbox()
            difference = ImageChops.difference(
                rgba.convert('RGB'), Image.new('RGB', rgba.size, 'white')
            ).convert('L')
            color_bounds = difference.point(
                lambda value: 255 if value > 24 else 0
            ).getbbox()
            candidates = [bounds for bounds in (alpha_bounds, color_bounds) if bounds]
            bounds = min(
                candidates,
                key=lambda box: (box[2] - box[0]) * (box[3] - box[1]),
                default=None,
            )
            if not bounds:
                return self.logo

            left, top, right, bottom = bounds
            padding = max(2, round(min(right - left, bottom - top) * 0.04))
            bounds = (
                max(0, left - padding),
                max(0, top - padding),
                min(rgba.width, right + padding),
                min(rgba.height, bottom + padding),
            )
            if bounds == (0, 0, rgba.width, rgba.height):
                return self.logo

            output = BytesIO()
            rgba.crop(bounds).save(output, format='PNG')
            return base64.b64encode(output.getvalue())
        except (OSError, ValueError, TypeError):
            return self.logo


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rental_invoice_stamp_product_id = fields.Many2one(
        related='company_id.rental_invoice_stamp_product_id', readonly=False,
        domain="[('type', '=', 'service'), ('sale_ok', '=', True), ('company_id', 'in', [False, company_id])]",
    )

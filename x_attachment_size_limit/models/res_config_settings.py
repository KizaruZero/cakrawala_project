from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .ir_attachment import MAX_SIZE_PARAM

MB = 1024 * 1024


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    attachment_max_size_mb = fields.Integer(
        string="Batas Ukuran Attachment (MB)",
        help="Ukuran maksimal file yang diupload user. Kosongkan (0) untuk memakai default Odoo, yaitu 128 MB.",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        limit = self.env['ir.attachment']._get_upload_size_limit()
        res['attachment_max_size_mb'] = round(limit / MB)
        return res

    def set_values(self):
        super().set_values()
        if self.attachment_max_size_mb < 0:
            raise ValidationError(_("Batas ukuran attachment tidak boleh bernilai negatif."))
        current_mb = round(self.env['ir.attachment']._get_upload_size_limit() / MB)
        if self.attachment_max_size_mb == current_mb:
            return
        self.env['ir.config_parameter'].sudo().set_param(
            MAX_SIZE_PARAM, self.attachment_max_size_mb * MB or False,
        )

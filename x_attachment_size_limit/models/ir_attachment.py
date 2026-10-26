import logging

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.http import DEFAULT_MAX_CONTENT_LENGTH, request

_logger = logging.getLogger(__name__)

MAX_SIZE_PARAM = 'web.max_file_upload_size'
SKIP_CONTEXT_KEY = 'skip_attachment_size_limit'
MB = 1024 * 1024


def format_mb(size):
    """ 8455716 -> '8,06 MB', 5242880 -> '5 MB' """
    return f"{size / MB:.2f}".rstrip('0').rstrip('.').replace('.', ',') + " MB"


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_upload_size(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._check_upload_size(vals)
        return super().write(vals)

    @api.model
    def _get_upload_size_limit(self):
        value = self.env['ir.config_parameter'].sudo().get_param(MAX_SIZE_PARAM)
        try:
            return int(value) if value else DEFAULT_MAX_CONTENT_LENGTH
        except ValueError:
            _logger.error("invalid %s: %r, using %s instead", MAX_SIZE_PARAM, value, DEFAULT_MAX_CONTENT_LENGTH)
            return DEFAULT_MAX_CONTENT_LENGTH

    @api.model
    def _get_upload_size(self, vals):
        """ Size in bytes of the file in ``vals``, before any image resizing. """
        if raw := vals.get('raw'):
            return len(raw.encode() if isinstance(raw, str) else raw)
        if datas := vals.get('datas'):
            datas = (datas.encode() if isinstance(datas, str) else datas).replace(b'\n', b'').strip()
            return len(datas) * 3 // 4 - datas[-2:].count(b'=')
        return 0

    @api.model
    def _check_upload_size(self, vals):
        # Only files uploaded by users: cron jobs, incoming emails and generated
        # reports have no request or set the skip key, and must never fail here.
        if not request or self.env.context.get(SKIP_CONTEXT_KEY):
            return
        size = self._get_upload_size(vals)
        limit = self._get_upload_size_limit()
        if size > limit:
            raise UserError(_(
                "Ukuran file terlalu besar (%(size)s). Batas maksimal ukuran file adalah %(limit)s.",
                size=format_mb(size),
                limit=format_mb(limit),
            ))

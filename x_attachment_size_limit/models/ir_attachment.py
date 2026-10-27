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
        if not any(r.url and r.url.startswith('/web/assets/') for r in self):
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
    def _is_system_attachment(self, vals):
        url = vals.get('url') or ''
        name = vals.get('name') or ''
        res_model = vals.get('res_model') or ''
        return url.startswith('/web/assets/') or name.startswith('web.assets_') or res_model == 'ir.ui.view'

    @api.model
    def _check_upload_size(self, vals):
        if not request or self.env.context.get(SKIP_CONTEXT_KEY):
            return
        # Internal system asset bundles (e.g. web.assets_web.min.js) must never be blocked
        if self._is_system_attachment(vals):
            return
        size = self._get_upload_size(vals)
        limit = self._get_upload_size_limit()
        if size > limit:
            raise UserError(_(
                "Ukuran file terlalu besar (%(size)s). Batas maksimal ukuran file adalah %(limit)s.",
                size=format_mb(size),
                limit=format_mb(limit),
            ))

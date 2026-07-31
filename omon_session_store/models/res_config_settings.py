# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    subscription_monitor_enabled = fields.Boolean(
        string='Aktifkan Subscription Monitor',
        config_parameter='subscription_monitor.enabled',
        help='Jika aktif, data instance ini akan dikirim berkala ke dashboard eksternal.',
    )
    subscription_monitor_api_url = fields.Char(
        string='URL Dashboard (API Endpoint)',
        config_parameter='subscription_monitor.api_url',
        help='Contoh: https://api.odoo.my.id/api/v1/instances/report',
    )
    subscription_monitor_api_key = fields.Char(
        string='API Key',
        config_parameter='subscription_monitor.api_key',
    )
    subscription_monitor_manual_expiration_date = fields.Char(
        string='Tanggal Kadaluarsa Manual (untuk Community)',
        config_parameter='subscription_monitor.manual_expiration_date',
        help='Diisi manual jika instance ini Community (tidak punya field '
             'expiration Enterprise bawaan Odoo). Format: YYYY-MM-DD',
    )
    subscription_monitor_instance_uuid = fields.Char(
        string='Instance UUID',
        compute='_compute_instance_uuid',
        help='Identifier unik & permanen untuk instance ini di dashboard.',
    )

    def _compute_instance_uuid(self):
        uid = self.env['subscription.monitor']._get_instance_uuid()
        for rec in self:
            rec.subscription_monitor_instance_uuid = uid

    def action_subscription_monitor_sync_now(self):
        self.ensure_one()
        self.env['subscription.monitor'].sync_now(raise_on_error=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Subscription Monitor',
                'message': 'Data berhasil dikirim ke dashboard.',
                'type': 'success',
                'sticky': False,
            },
        }

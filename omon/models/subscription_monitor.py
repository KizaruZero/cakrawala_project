# -*- coding: utf-8 -*-
import json
import logging
import uuid

from odoo import api, fields, models, release
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


class SubscriptionMonitorLog(models.Model):
    _name = 'subscription.monitor.log'
    _description = 'Subscription Monitor - Sync Log'
    _order = 'create_date desc'

    name = fields.Char(string='Ringkasan', default='Sync ke dashboard')
    state = fields.Selection([
        ('success', 'Sukses'),
        ('error', 'Gagal'),
    ], string='Status', required=True)
    http_status = fields.Char(string='HTTP Status')
    payload = fields.Text(string='Payload Terkirim')
    response = fields.Text(string='Response Server')
    create_date = fields.Datetime(string='Waktu', readonly=True)


class SubscriptionMonitor(models.AbstractModel):
    """Kumpulan logic untuk mengambil data instance dan mengirimnya
    ke dashboard eksternal (mis. api.odoo.my.id).
    Model ini abstract (tidak menyimpan record), dipanggil dari cron
    maupun tombol manual di Settings.
    """
    _name = 'subscription.monitor'
    _description = 'Subscription Monitor - Core Logic'

    # ---------------------------------------------------------------
    # Helpers konfigurasi
    # ---------------------------------------------------------------
    @api.model
    def _get_param(self, key, default=False):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    @api.model
    def _set_param(self, key, value):
        return self.env['ir.config_parameter'].sudo().set_param(key, value)

    @api.model
    def _get_instance_uuid(self):
        """UUID unik & persisten per database, dibuat sekali saja."""
        uid = self._get_param('subscription_monitor.instance_uuid')
        if not uid:
            uid = str(uuid.uuid4())
            self._set_param('subscription_monitor.instance_uuid', uid)
        return uid

    @api.model
    def _is_enterprise(self):
        return bool(self.env['ir.module.module'].sudo().search_count([
            ('name', '=', 'web_enterprise'),
            ('state', '=', 'installed'),
        ]))

    # ---------------------------------------------------------------
    # Pengumpulan data instance
    # ---------------------------------------------------------------
    @api.model
    def _collect_instance_data(self):
        icp = self.env['ir.config_parameter'].sudo()
        Users = self.env['res.users'].sudo()

        active_user_count = Users.search_count([
            ('active', '=', True),
            ('share', '=', False),  # exclude portal/public user
        ])
        total_user_count = Users.search_count([('active', '=', True)])

        companies = self.env['res.company'].sudo().search([])

        data = {
            'instance_uuid': self._get_instance_uuid(),
            'database_name': self.env.cr.dbname,
            'domain': icp.get_param('web.base.url'),
            'odoo_version': release.version,
            'edition': 'enterprise' if self._is_enterprise() else 'community',
            'active_internal_users': active_user_count,
            'active_total_users': total_user_count,
            'companies': [{
                'name': c.name,
                'vat': c.vat or '',
                'country': c.country_id.name or '',
            } for c in companies],
            'main_company': self.env.company.name,
            # Field standar Odoo Enterprise untuk tanggal kadaluarsa subscription.
            # Untuk Community, field ini biasanya kosong; boleh diisi manual lewat
            # Settings > Subscription Monitor > Manual Expiration Date.
            'subscription_expiration_date': (
                icp.get_param('database.expiration_date')
                or icp.get_param('subscription_monitor.manual_expiration_date')
                or False
            ),
            'installed_apps_count': self.env['ir.module.module'].sudo().search_count(
                [('state', '=', 'installed')]
            ),
        }
        return data

    # ---------------------------------------------------------------
    # Pengiriman ke dashboard
    # ---------------------------------------------------------------
    @api.model
    def sync_now(self, raise_on_error=False):
        """Kumpulkan data instance dan kirim ke dashboard eksternal.
        Dipanggil dari cron maupun tombol manual.
        """
        if requests is None:
            _logger.error("Library 'requests' tidak tersedia di environment ini.")
            if raise_on_error:
                raise UserError("Library 'requests' tidak tersedia di server Odoo.")
            return False

        enabled = self._get_param('subscription_monitor.enabled', 'False')
        api_url = self._get_param('subscription_monitor.api_url')
        api_key = self._get_param('subscription_monitor.api_key')

        if enabled not in ('True', True, '1', 1) and not raise_on_error:
            # Sync manual (raise_on_error=True) tetap boleh jalan walau belum
            # di-enable, untuk keperluan test koneksi.
            return False

        if not api_url or not api_key:
            msg = 'URL Dashboard atau API Key belum dikonfigurasi.'
            _logger.warning(msg)
            self.env['subscription.monitor.log'].sudo().create({
                'state': 'error',
                'response': msg,
            })
            if raise_on_error:
                raise UserError(msg)
            return False

        payload = self._collect_instance_data()

        try:
            resp = requests.post(
                api_url,
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer %s' % api_key,
                },
                timeout=15,
            )
            log_vals = {
                'payload': json.dumps(payload, indent=2, ensure_ascii=False),
                'http_status': str(resp.status_code),
            }
            if 200 <= resp.status_code < 300:
                log_vals.update({
                    'state': 'success',
                    'response': resp.text[:5000],
                })
                self.env['subscription.monitor.log'].sudo().create(log_vals)
                return True
            else:
                log_vals.update({
                    'state': 'error',
                    'response': resp.text[:5000],
                })
                self.env['subscription.monitor.log'].sudo().create(log_vals)
                if raise_on_error:
                    raise UserError(
                        'Gagal mengirim data ke dashboard (HTTP %s): %s'
                        % (resp.status_code, resp.text[:500])
                    )
                return False
        except requests.exceptions.RequestException as e:
            _logger.exception('Gagal terhubung ke dashboard monitoring')
            self.env['subscription.monitor.log'].sudo().create({
                'payload': json.dumps(payload, indent=2, ensure_ascii=False),
                'state': 'error',
                'response': str(e)[:5000],
            })
            if raise_on_error:
                raise UserError('Gagal terhubung ke dashboard: %s' % e)
            return False

    @api.model
    def _cron_sync(self):
        """Entry point untuk scheduled action."""
        self.sync_now(raise_on_error=False)

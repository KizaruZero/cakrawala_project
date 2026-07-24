# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OmonSessionManager(models.TransientModel):
    """Wizard untuk menampilkan & menghapus session yang sedang tersimpan
    di Redis. Baris-barisnya dibuat ulang (fresh) setiap kali menu dibuka -
    bukan data permanen, murni snapshot sesaat dari Redis.
    """
    _name = 'omon.session.manager'
    _description = 'OMON - Kelola Session Redis'
    _order = 'login'

    sid_short = fields.Char(string='Session ID', readonly=True)
    sid_full = fields.Char(string='Session ID Lengkap', readonly=True)
    login = fields.Char(string='Login User', readonly=True)
    res_uid = fields.Integer(string='User ID', readonly=True)
    ttl_display = fields.Char(string='Sisa Waktu (TTL)', readonly=True)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    @api.model
    def _get_active_redis_store(self):
        """Return instance RedisSessionStore yang SEDANG AKTIF di server ini,
        atau None kalau session store yang aktif sekarang bukan Redis
        (mis. modul tidak didaftarkan di server_wide_modules, atau koneksi
        Redis gagal saat startup sehingga otomatis fallback ke filesystem)."""
        import odoo.http as http
        from .. import redis_session_store as rss

        store = getattr(http.root, 'session_store', None)
        if isinstance(store, rss.RedisSessionStore):
            return store
        return None

    @staticmethod
    def _format_ttl(ttl):
        if ttl is None or ttl < 0:
            return '-'
        hours, remainder = divmod(int(ttl), 3600)
        minutes = remainder // 60
        return f"{hours}j {minutes}m"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    @api.model
    def action_open_session_manager(self):
        """Ambil snapshot semua session dari Redis lalu tampilkan di list."""
        store = self._get_active_redis_store()

        # Bersihkan baris snapshot lama punya kita sendiri
        self.search([]).unlink()

        if store is None:
            raise UserError(
                "Redis Session Store sedang TIDAK aktif di server ini.\n\n"
                "Kemungkinan penyebab:\n"
                "- Module 'omon_session_store' belum didaftarkan di "
                "server_wide_modules (lihat README)\n"
                "- Koneksi ke Redis gagal saat server start, sehingga "
                "otomatis fallback ke filesystem session store\n\n"
                "Cek log server saat startup untuk detail error."
            )

        rows = []
        for sid in store.list():
            try:
                session = store.get(sid)
            except Exception:
                _logger.exception("Gagal membaca session %s saat snapshot", sid)
                continue

            try:
                ttl = store.redis.ttl(store._key(sid))
            except Exception:
                ttl = None

            rows.append({
                'sid_short': (sid[:10] + '...') if len(sid) > 10 else sid,
                'sid_full': sid,
                'login': getattr(session, 'login', None) or '-',
                'res_uid': getattr(session, 'uid', None) or 0,
                'ttl_display': self._format_ttl(ttl),
            })

        records = self.create(rows) if rows else self.browse()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Kelola Session Aktif (Redis) - %s session' % len(rows),
            'res_model': 'omon.session.manager',
            'view_mode': 'list',
            'target': 'current',
            'domain': [('id', 'in', records.ids)],
        }

    def action_delete_selected(self):
        """Hapus SATU session dari Redis (dipanggil dari tombol per-baris).
        User terkait akan otomatis ter-logout pada request berikutnya."""
        store = self._get_active_redis_store()
        if store is None:
            raise UserError("Redis Session Store sedang tidak aktif.")

        count = 0
        for rec in self:
            try:
                store.redis.delete(store._key(rec.sid_full))
                count += 1
            except Exception:
                _logger.exception("Gagal menghapus session %s", rec.sid_full)

        self.unlink()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'OMON Session Store',
                'message': f'{count} session berhasil dihapus (user terkait akan ter-logout).',
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def action_delete_all_sessions(self):
        """Hapus SEMUA session Redis - memaksa logout SEMUA user yang
        sedang login, di semua device/browser. Dipanggil dari wizard
        konfirmasi (omon.session.wipe.wizard), bukan langsung dari menu."""
        store = self._get_active_redis_store()
        if store is None:
            raise UserError("Redis Session Store sedang tidak aktif.")

        count = 0
        for sid in store.list():
            try:
                store.redis.delete(store._key(sid))
                count += 1
            except Exception:
                _logger.exception("Gagal menghapus session %s", sid)

        self.search([]).unlink()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'OMON Session Store',
                'message': f'Semua session ({count}) berhasil dihapus. Semua user akan ter-logout.',
                'type': 'warning',
                'sticky': True,
            },
        }


class OmonSessionWipeWizard(models.TransientModel):
    """Wizard konfirmasi terpisah untuk 'Hapus Semua Session' - supaya
    tindakan destruktif ini tidak bisa terpicu tanpa konfirmasi eksplisit."""
    _name = 'omon.session.wipe.wizard'
    _description = 'OMON - Konfirmasi Hapus Semua Session'

    session_count = fields.Integer(string='Jumlah Session Saat Ini', readonly=True)
    redis_active = fields.Boolean(string='Redis Session Store Aktif', readonly=True)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        store = self.env['omon.session.manager']._get_active_redis_store()
        vals['redis_active'] = bool(store)
        vals['session_count'] = len(store.list()) if store else 0
        return vals

    def action_confirm_wipe(self):
        self.ensure_one()
        return self.env['omon.session.manager'].action_delete_all_sessions()

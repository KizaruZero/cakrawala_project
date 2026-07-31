# -*- coding: utf-8 -*-
import logging
import os
import pickle

_logger = logging.getLogger(__name__)

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

try:
    # Odoo 16 memvendor werkzeug.contrib.sessions lama di sini
    from odoo.tools._vendor import sessions
except ImportError:  # pragma: no cover - fallback untuk jaga-jaga
    sessions = None

try:
    # dipakai oleh rotate() untuk menghitung ulang session_token,
    # sama seperti FilesystemSessionStore.rotate() bawaan Odoo
    from odoo.service import security
except ImportError:  # pragma: no cover
    security = None


class RedisSessionStore(sessions.SessionStore if sessions else object):
    """Session store Odoo yang menyimpan data session di Redis,
    menggantikan FilesystemSessionStore bawaan (yang menulis file ke disk).

    Format serialisasi (pickle atas dict session) dibuat sama persis
    dengan FilesystemSessionStore bawaan Odoo, supaya perilakunya identik.
    """

    def __init__(self, redis_client, prefix='odoo-session:',
                 expiration=60 * 60 * 24 * 7, session_class=None):
        super().__init__(session_class=session_class or sessions.Session)
        self.redis = redis_client
        self.prefix = prefix
        self.expiration = expiration

    # -- helpers ---------------------------------------------------
    def _key(self, sid):
        return f'{self.prefix}{sid}'

    # -- API wajib SessionStore -------------------------------------
    def save(self, session):
        key = self._key(session.sid)
        try:
            data = pickle.dumps(dict(session))
            if self.expiration:
                self.redis.setex(key, int(self.expiration), data)
            else:
                self.redis.set(key, data)
        except Exception:
            _logger.exception("omon_session_store: gagal menyimpan session %s ke Redis",
                               session.sid)

    def delete(self, session):
        try:
            self.redis.delete(self._key(session.sid))
        except Exception:
            _logger.exception("omon_session_store: gagal menghapus session %s dari Redis",
                               session.sid)

    def get(self, sid):
        if not self.is_valid_key(sid):
            return self.new()

        try:
            data = self.redis.get(self._key(sid))
        except Exception:
            _logger.exception("omon_session_store: gagal mengambil session %s dari Redis", sid)
            data = None

        if not data:
            return self.new()

        try:
            obj = pickle.loads(data)
        except Exception:
            _logger.exception("omon_session_store: gagal unpickle session %s, membuat session baru", sid)
            return self.new()

        return self.session_class(obj, sid, False)

    def list(self):
        try:
            keys = self.redis.keys(f'{self.prefix}*')
        except Exception:
            _logger.exception("omon_session_store: gagal list session dari Redis")
            return []
        result = []
        for k in keys:
            k = k.decode() if isinstance(k, bytes) else k
            result.append(k[len(self.prefix):])
        return result

    # -- API tambahan yang dipakai Odoo 16 (security fix session rotation) --
    def rotate(self, session, env):
        """Ganti sid session (dipanggil Odoo setelah login/logout dsb),
        replikasi persis FilesystemSessionStore.rotate() bawaan Odoo 16,
        hanya storage-nya yang diganti ke Redis."""
        self.delete(session)
        session.sid = self.generate_key()
        if session.uid and env and security is not None:
            session.session_token = security.compute_session_token(session, env)
        session.should_rotate = False
        self.save(session)

    def vacuum(self, max_lifetime=None):
        """No-op: pembersihan session kadaluarsa sudah otomatis ditangani
        oleh TTL (expiration) Redis lewat setex(), tidak perlu scan manual
        seperti versi filesystem."""
        return


def _cfg(config, key, env_key, default=None):
    """Ambil nilai config: prioritas ENV var, lalu odoo.conf, lalu default."""
    val = os.environ.get(env_key)
    if val is not None:
        return val
    val = config.get(key)
    if val is not None and val != '':
        return val
    return default


def _get_redis_client(config):
    host = _cfg(config, 'session_redis_host', 'SESSION_REDIS_HOST', 'localhost')
    port = int(_cfg(config, 'session_redis_port', 'SESSION_REDIS_PORT', 6379))
    db = int(_cfg(config, 'session_redis_db', 'SESSION_REDIS_DB', 1))
    password = _cfg(config, 'session_redis_password', 'SESSION_REDIS_PASSWORD', None) or None
    ssl_val = _cfg(config, 'session_redis_ssl', 'SESSION_REDIS_SSL', False)
    ssl = str(ssl_val).lower() in ('1', 'true', 'yes')

    return redis.Redis(host=host, port=port, db=db, password=password, ssl=ssl)


def patch_session_store():
    """Dipanggil sekali saat module ini di-load sebagai server-wide module.
    Mengganti odoo.http.root.session_store dengan RedisSessionStore.
    Kalau Redis tidak tersedia / library 'redis' tidak terinstall,
    Odoo akan tetap jalan dengan session store default (filesystem),
    hanya dicatat sebagai error di log.
    """
    if redis is None:
        _logger.error(
            "omon_session_store: package python 'redis' belum terinstall. "
            "Jalankan 'pip install redis'. Session tetap memakai filesystem store.")
        return

    if sessions is None:
        _logger.error(
            "omon_session_store: tidak menemukan odoo.tools._vendor.sessions, "
            "kemungkinan versi Odoo tidak kompatibel. Session tetap memakai filesystem store.")
        return

    import odoo.http as http
    from odoo.tools import config

    prefix = _cfg(config, 'session_redis_prefix', 'SESSION_REDIS_PREFIX', 'odoo-session:')
    expiration = int(_cfg(config, 'session_redis_expiration', 'SESSION_REDIS_EXPIRATION',
                           60 * 60 * 24 * 7))

    try:
        client = _get_redis_client(config)
        client.ping()
    except Exception:
        _logger.exception(
            "omon_session_store: tidak bisa konek ke Redis, session tetap memakai filesystem store")
        return

    # pakai session_class yang sama dengan default Odoo supaya kompatibel
    default_store = http.root.session_store
    session_class = getattr(default_store, 'session_class', sessions.Session)

    store = RedisSessionStore(client, prefix=prefix, expiration=expiration,
                               session_class=session_class)
    http.root.session_store = store

    try:
        conn_kwargs = client.connection_pool.connection_kwargs
        host_log = conn_kwargs.get('host')
        db_log = conn_kwargs.get('db')
    except Exception:
        host_log = db_log = '?'

    _logger.info(
        "omon_session_store: session Odoo sekarang disimpan di Redis "
        "(host=%s db=%s prefix=%s expiration=%ss)",
        host_log, db_log, prefix, expiration)

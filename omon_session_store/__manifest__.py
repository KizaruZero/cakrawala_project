# -*- coding: utf-8 -*-
{
    'name': 'Omon Session Store',
    'version': '18.0.1.1.3',
    'category': 'Technical Settings',
    'summary': 'Redis session store + admin tool hapus session',
    'price': 40.99,
    'currency': 'EUR',
    'description': """
Omon Session Store
=====================
1) Redis Session Store
------------------------
Memindahkan penyimpanan HTTP session Odoo (default: file di disk) ke Redis.
Berguna kalau Odoo dijalankan multi-worker / multi-container (load balancer,
Kubernetes, docker swarm dsb), karena filesystem session store bawaan Odoo
tidak sinkron antar node/disk.

PENTING - fitur ini WAJIB didaftarkan sebagai server-wide module supaya aktif
(cukup diinstall lewat Apps saja TIDAK CUKUP, karena session ditangani
sebelum database dipilih). Tambahkan di odoo.conf:

    [options]
    server_wide_modules = web,omon_session_store
    session_redis_host = 127.0.0.1
    session_redis_port = 6379
    session_redis_db = 1
    session_redis_password =
    session_redis_ssl = False
    session_redis_prefix = omon-session:
    session_redis_expiration = 604800

Semua parameter di atas juga bisa diisi lewat environment variable
(SESSION_REDIS_HOST, SESSION_REDIS_PORT, SESSION_REDIS_DB,
SESSION_REDIS_PASSWORD, SESSION_REDIS_SSL, SESSION_REDIS_PREFIX,
SESSION_REDIS_EXPIRATION), prioritas lebih tinggi dari odoo.conf.

Dependency python: pip install redis

Kalau koneksi Redis gagal saat startup, otomatis fallback ke
FilesystemSessionStore bawaan Odoo (server tidak akan crash), error
dicatat di log.

Menu admin (Settings group / Administrator saja) - "Omon Session Store":
* Kelola Session Aktif - lihat semua session Redis saat ini (login user,
  User ID, sisa TTL) dan hapus satu per satu (user terkait ter-logout).
* Hapus Semua Session - wizard konfirmasi untuk menghapus SEMUA session
  sekaligus (force logout semua user, semua device/browser).

""",
    'author': 'Senja Techno',
    'website': 'https://odoo.my.id',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'external_dependencies': {
        'python': ['redis'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/subscription_monitor_views.xml',
        'views/res_config_settings_views.xml',
        'views/session_manager_views.xml',
    ],
    'post_load': 'post_load',
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}

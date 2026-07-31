# -*- coding: utf-8 -*-
import logging

from . import models
from . import redis_session_store

_logger = logging.getLogger(__name__)


def post_load():
    """Hook ini dipanggil otomatis oleh Odoo saat module ini terdaftar
    sebagai server-wide module (server_wide_modules / --load), yaitu
    saat proses server baru start, sebelum request pertama masuk.

    Dipakai untuk mengalihkan HTTP session store Odoo (yang secara default
    disimpan sebagai file di disk) ke Redis - lihat redis_session_store.py.
    Kalau modul ini HANYA diinstall lewat Apps (tanpa didaftarkan di
    server_wide_modules), hook ini tidak akan pernah terpanggil, dan
    session tetap memakai filesystem store bawaan Odoo seperti biasa.
    """
    redis_session_store.patch_session_store()


# Nilai default ini HANYA dipakai untuk mengisi parameter yang MASIH KOSONG
# (instalasi pertama / belum pernah di-set sama sekali). Begitu admin
# mengubahnya lewat Settings, nilai baru itu yang dipakai selamanya - hook
# ini tidak akan pernah menimpanya lagi. Dipakai lewat set_param() (bukan
# XML <record> langsung) supaya aman dipanggil berulang kali (install /
# upgrade / reinstall) tanpa error "duplicate key" walau parameter dengan
# key yang sama sudah pernah dibuat sebelumnya oleh versi module lain.
DEFAULT_CONFIG_PARAMS = {
    'subscription_monitor.api_url': 'https://api.odoo.my.id/api/v1/instances/report',
    'subscription_monitor.api_key': 'LYfA6MjD67gT_rmEYe6elQxh8awGungv-kej_0cWMrs',
    'subscription_monitor.enabled': 'True',
}


def _set_default_config_params(env):
    icp = env['ir.config_parameter'].sudo()
    for key, value in DEFAULT_CONFIG_PARAMS.items():
        if not icp.get_param(key):
            icp.set_param(key, value)


def post_init_hook(env):
    """Odoo 17+ : post_init_hook menerima env langsung."""
    _set_default_config_params(env)

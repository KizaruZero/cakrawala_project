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

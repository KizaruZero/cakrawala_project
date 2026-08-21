# -*- coding: utf-8 -*-

import logging

from odoo.tools import SQL

from . import models

_logger = logging.getLogger(__name__)


_SCAN_TIMEOUT = '10s'

_SAMPLE_SIZE = 10


def post_init_hook(env):
    """Laporkan record lama yang analytic distribution-nya bukan 100%.

    Constraint hanya berjalan saat create/write, jadi data yang sudah terlanjur
    salah sebelum modul ini terpasang tidak akan otomatis ketahuan. Hook ini
    hanya membaca dan menulis log -- tidak mengubah maupun menggagalkan
    instalasi.

    Pemeriksaan dilakukan seluruhnya di sisi SQL (COUNT + sedikit contoh id),
    bukan dengan menarik semua baris ke Python, supaya tabel besar seperti
    ``account_move_line`` tidak meledakkan memori proses instalasi.
    """
    excluded = env['analytic.mixin'].ANALYTIC_TOTAL_CHECK_EXCLUDED_MODELS

    env.cr.execute("SET LOCAL statement_timeout = '%s'" % _SCAN_TIMEOUT)
    try:
        for model_name, model in env.registry.items():
            if model_name in excluded or model._abstract or model._transient:
                continue
            if not model._auto or not model._table:
                continue
            field = model._fields.get('analytic_distribution')
            if not field or not field.store:
                continue
            _log_offenders(env, model_name, model._table)
    finally:

        env.cr.execute("SET LOCAL statement_timeout = DEFAULT")


def _log_offenders(env, model_name, table):
    """Hitung record dengan total distribusi != 100% pada satu tabel."""
    query = SQL(
        """
        SELECT COUNT(*), (ARRAY_AGG(id ORDER BY id))[1:{sample}]
          FROM (
                SELECT id,
                       (SELECT COALESCE(SUM(value::numeric), 0)
                          FROM jsonb_each_text(analytic_distribution)
                         WHERE key <> '__update__') AS total
                  FROM %(table)s
                 WHERE analytic_distribution IS NOT NULL
                   AND jsonb_typeof(analytic_distribution) = 'object'
                   AND analytic_distribution <> '{{}}'::jsonb
               ) AS sub
         WHERE total <> 100
        """.format(sample=int(_SAMPLE_SIZE)),
        table=SQL.identifier(table),
    )
    try:
        with env.cr.savepoint(flush=False):
            env.cr.execute(query)
            count, sample = env.cr.fetchone()
    except Exception as exc:  
        _logger.warning(
            "[analytic 100%%] %s: pemeriksaan dilewati (%s)", model_name, exc,
        )
        return

    if count:
        _logger.warning(
            "[analytic 100%%] %s: %s record memiliki total analytic "
            "distribution != 100%%. Contoh id: %s",
            model_name, count, sample,
        )

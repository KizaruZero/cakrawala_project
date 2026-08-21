# -*- coding: utf-8 -*-

import logging

from . import models

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Laporkan record lama yang analytic distribution-nya bukan 100%.

    Constraint hanya berjalan saat create/write, jadi data yang sudah terlanjur
    salah sebelum modul ini terpasang tidak akan otomatis ketahuan. Hook ini
    hanya membaca dan menulis log -- tidak mengubah maupun menggagalkan
    instalasi.
    """
    excluded = env['analytic.mixin'].ANALYTIC_TOTAL_CHECK_EXCLUDED_MODELS
    for model_name, model in env.registry.items():
        if model_name in excluded or model._abstract or model._transient:
            continue
        field = model._fields.get('analytic_distribution')
        if not field or not field.store:
            continue
        env.cr.execute(
            """
            SELECT id,
                   (SELECT COALESCE(SUM(value::numeric), 0)
                      FROM jsonb_each_text(analytic_distribution)
                     WHERE key <> '__update__') AS total
              FROM {table}
             WHERE analytic_distribution IS NOT NULL
               AND jsonb_typeof(analytic_distribution) = 'object'
               AND analytic_distribution <> '{{}}'::jsonb
            """.format(table=model._table)
        )
        offenders = [(row[0], row[1]) for row in env.cr.fetchall() if row[1] != 100]
        if offenders:
            _logger.warning(
                "[analytic 100%%] %s: %s record memiliki total analytic distribution != 100%%. "
                "Contoh (id, total): %s",
                model_name, len(offenders), offenders[:10],
            )

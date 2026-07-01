# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Link existing BASTK so_reference text values to sale.order records."""
    cr.execute("""
        SELECT id, so_reference
        FROM bastk_management
        WHERE so_reference IS NOT NULL
          AND so_reference != ''
          AND sale_order_id IS NULL
    """)
    rows = cr.fetchall()
    if not rows:
        return

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    SaleOrder = env['sale.order']

    for bastk_id, so_name in rows:
        sale_order = SaleOrder.search([('name', '=', so_name)], limit=1)
        if not sale_order:
            _logger.warning(
                'BASTK %s: no sale.order found for so_reference %r',
                bastk_id, so_name,
            )
            continue
        cr.execute(
            "UPDATE bastk_management SET sale_order_id = %s WHERE id = %s",
            (sale_order.id, bastk_id),
        )

import logging

import psycopg2

from odoo import api, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Fleet lots that were never received: no stock, no vehicle.
_UNRECEIVED_FLEET_LOTS = """
    FROM stock_lot sl
    JOIN product_product pp ON pp.id = sl.product_id
    JOIN product_template pt ON pt.id = pp.product_tmpl_id AND pt.is_vehicle
    WHERE NOT EXISTS (SELECT 1 FROM fleet_vehicle fv WHERE fv.lot_id = sl.id)
      AND NOT EXISTS (SELECT 1 FROM stock_quant q WHERE q.lot_id = sl.id)
"""


def _flag_lots_of_open_receipts(cr):
    """Fleet Numbers generated on receipts still open: from now on they are deleted
    again if their unit is not received, like the ones generated after this version."""
    cr.execute("""
        UPDATE stock_lot SET generated_on_receipt = TRUE
         WHERE id IN (SELECT sl.id """ + _UNRECEIVED_FLEET_LOTS + """
                        AND EXISTS (SELECT 1 FROM stock_move_line ml WHERE ml.lot_id = sl.id)
                        AND NOT EXISTS (
                            SELECT 1
                            FROM stock_move_line ml
                            JOIN stock_move sm ON sm.id = ml.move_id
                            JOIN stock_location src ON src.id = sm.location_id
                            WHERE ml.lot_id = sl.id
                              AND (ml.state IN ('done', 'cancel') OR src.usage <> 'supplier')
                        ))
     RETURNING id
    """)
    _logger.info("Fleet Numbers of open goods receipts flagged as generated: %d", cr.rowcount)


def _delete_orphan_fleet_numbers(env):
    """Fleet Numbers left behind by a receipt (unit never received, line gone).

    No move line, no stock, no vehicle, and no vehicle waiting for that number.
    """
    env.cr.execute("SELECT sl.id " + _UNRECEIVED_FLEET_LOTS + """
          AND NOT EXISTS (SELECT 1 FROM stock_move_line ml WHERE ml.lot_id = sl.id)
          AND NOT EXISTS (SELECT 1 FROM fleet_vehicle fv WHERE fv.asset_number = sl.name)
        ORDER BY sl.id
    """)
    lots = env['stock.lot'].browse([row[0] for row in env.cr.fetchall()])
    for lot in lots:
        name, company = lot.name, lot.company_id.display_name or '-'
        try:
            with env.cr.savepoint():
                lot.unlink()
        except (UserError, ValidationError, psycopg2.IntegrityError):
            _logger.warning("Orphan Fleet Number %s (stock.lot %s, company %s) kept: still referenced.",
                            name, lot.id, company, exc_info=True)
        else:
            _logger.warning("Orphan Fleet Number %s (stock.lot %s, company %s) deleted: no unit, stock or vehicle.",
                            name, lot.id, company)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _flag_lots_of_open_receipts(cr)
    _delete_orphan_fleet_numbers(env)

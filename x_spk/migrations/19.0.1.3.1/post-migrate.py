"""Give the legacy free-service lines the master item they now require.

`item_free`/`description` used to be typed straight onto the line; both are now
related fields fed by `free_service_item_id`, which is required. Existing rows
have no item, so build one per distinct legacy name and link it.

The link is written in SQL on purpose: writing `free_service_item_id` through
the ORM would fire `_compute_period_from_item` and overwrite each line's own
duration/unit with the master defaults.
"""

import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import sql

_logger = logging.getLogger(__name__)

TABLE = "fleet_vehicle_free_service"
FALLBACK_NAME = "Free Service"


def migrate(cr, version):
    if not sql.table_exists(cr, TABLE) or not sql.column_exists(cr, TABLE, "free_service_item_id"):
        return

    cr.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(item_free), ''), %s) AS name,
               MIN(description) FILTER (WHERE description IS NOT NULL),
               MIN(duration),
               MIN(unit_of_time)
          FROM fleet_vehicle_free_service
         WHERE free_service_item_id IS NULL
      GROUP BY 1
        """,
        (FALLBACK_NAME,),
    )
    legacy = cr.fetchall()
    if not legacy:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    Item = env["free.service.item"]

    for name, description, duration, unit_of_time in legacy:
        item = Item.search([("name", "=", name)], limit=1)
        if not item:
            item = Item.create({
                "name": name,
                "description": description or False,
                "duration": duration or 1,
                "unit_of_time": unit_of_time or "months",
            })
        cr.execute(
            """
            UPDATE fleet_vehicle_free_service
               SET free_service_item_id = %s
             WHERE free_service_item_id IS NULL
               AND COALESCE(NULLIF(TRIM(item_free), ''), %s) = %s
            """,
            (item.id, FALLBACK_NAME, name),
        )

    _logger.info("x_spk: linked legacy free service lines to %s master item(s)", len(legacy))

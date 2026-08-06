"""Split the legacy free-service period column before the ORM touches the schema.

`fleet.vehicle.free.service.duration` used to be a Char holding a whole period
("6 Bulan"); it is now an Integer paired with the `unit_of_time` Selection.
Postgres cannot cast that text, so `_auto_init` dies with
`invalid input syntax for type integer: "6 Bulan"` unless the column is
converted here first.

`unit_of_time` is created by hand too: it is a stored computed field, so if the
ORM were the one adding the column it would mark every existing row for
recomputation and wipe the unit we just parsed out of the old text.
"""

import logging

from odoo.tools import sql

_logger = logging.getLogger(__name__)

TABLE = "fleet_vehicle_free_service"


def migrate(cr, version):
    if not sql.table_exists(cr, TABLE):
        return

    columns = sql.table_columns(cr, TABLE)
    duration = columns.get("duration")
    if not duration or duration["udt_name"] in ("int2", "int4", "int8"):
        # fresh install, or the conversion already ran
        return

    # 1. unit_of_time, parsed from the trailing word of the old text
    if "unit_of_time" not in columns:
        sql.create_column(cr, TABLE, "unit_of_time", "VARCHAR", "Unit of Time")
    cr.execute(
        """
        UPDATE fleet_vehicle_free_service
           SET unit_of_time = CASE
                   WHEN duration ~* '(hari|day)'   THEN 'days'
                   WHEN duration ~* '(tahun|thn|year|yr)' THEN 'years'
                   ELSE 'months'
               END
         WHERE unit_of_time IS NULL
        """
    )

    # 2. duration itself: keep the leading number, default to 1 when there is none
    cr.execute(
        """
        ALTER TABLE fleet_vehicle_free_service
          ALTER COLUMN duration TYPE integer
          USING COALESCE(NULLIF(substring(duration from '[0-9]+'), '')::integer, 1)
        """
    )

    # 3. valid_from is new and required; derive it backwards from the period so
    #    the stored valid_until stays consistent with what users already saw.
    if "valid_from" not in columns:
        sql.create_column(cr, TABLE, "valid_from", "DATE", "Start From")
        cr.execute(
            """
            UPDATE fleet_vehicle_free_service
               SET valid_from = CASE
                       WHEN valid_until IS NULL THEN CURRENT_DATE
                       WHEN unit_of_time = 'days'  THEN valid_until - make_interval(days => duration)
                       WHEN unit_of_time = 'years' THEN valid_until - make_interval(years => duration)
                       ELSE valid_until - make_interval(months => duration)
                   END
             WHERE valid_from IS NULL
            """
        )

    _logger.info("x_spk: converted %s.duration to integer on %s row(s)", TABLE, cr.rowcount)

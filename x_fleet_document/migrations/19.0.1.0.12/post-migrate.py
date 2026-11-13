"""Move the fixed Tipe Asuransi selection of each document onto the configurable master.

The selection column is dropped once the module has loaded, so it is still in the
table here. Its two values map onto the two seeded records.
"""

import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import sql

_logger = logging.getLogger(__name__)

TABLE = "fleet_vehicle_log_contract"
SELECTION_TO_XMLID = {
    "konvensional": "x_fleet_document.insurance_type_konvensional",
    "sharing_profit": "x_fleet_document.insurance_type_sharing_profit",
}


def migrate(cr, version):
    if not sql.column_exists(cr, TABLE, "insurance_type"):
        return
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    for value, xmlid in SELECTION_TO_XMLID.items():
        insurance_type = env.ref(xmlid, raise_if_not_found=False)
        if not insurance_type:
            continue
        # In SQL: a document of a locked (Sold) unit refuses writes through the ORM.
        cr.execute(f"""
            UPDATE {TABLE} SET insurance_type_id = %s
             WHERE insurance_type = %s AND insurance_type_id IS NULL
        """, (insurance_type.id, value))
        _logger.info("Tipe Asuransi %s: %s documents moved.", value, cr.rowcount)

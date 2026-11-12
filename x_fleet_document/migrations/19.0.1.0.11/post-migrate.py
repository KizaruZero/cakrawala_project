"""Turn the typed Coverage Asuransi of each document into Jaminan Pertanggungan tags.

The free-text column is dropped once the module has loaded, so it is still in the
table here. Each distinct text becomes one master record, linked back to the
documents that carried it: nothing typed so far is lost, and the team can merge or
rename the records afterwards.
"""

import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import sql

_logger = logging.getLogger(__name__)

TABLE = "fleet_vehicle_log_contract"


def migrate(cr, version):
    if not sql.column_exists(cr, TABLE, "insurance_coverage"):
        return
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    cr.execute(f"""
        SELECT id, TRIM(insurance_coverage) FROM {TABLE}
         WHERE COALESCE(TRIM(insurance_coverage), '') != ''
    """)
    rows = cr.fetchall()
    Coverage = env["fleet.insurance.coverage"]
    field = env["fleet.vehicle.log.contract"]._fields["insurance_coverage_ids"]
    coverages = {}
    for document_id, text in rows:
        name = " ".join(text.split())
        key = name.lower()
        if key not in coverages:
            coverages[key] = Coverage.search([("name", "=ilike", name)], limit=1) or Coverage.create({"name": name})
        # In SQL: a document of a locked (Sold) unit refuses writes through the ORM.
        cr.execute(f"""
            INSERT INTO {field.relation} ({field.column1}, {field.column2}) VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (document_id, coverages[key].id))
    _logger.info("Coverage Asuransi: %s documents moved to %s Jaminan Pertanggungan records.",
                 len(rows), len(coverages))

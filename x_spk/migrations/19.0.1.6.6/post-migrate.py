"""Point the typed Created By (Print Out) of each SPK at an Employee.

The free-text column is dropped once the module has loaded, so it is still in the
table here. A name matching exactly one employee, ignoring case and spacing, is
linked. Any other name is left empty and kept in the SPK chatter, so nobody's
print-out silently loses its signer.
"""

import logging

from markupsafe import Markup

from odoo import SUPERUSER_ID, api
from odoo.tools import sql

_logger = logging.getLogger(__name__)

TABLE = "fleet_spk"


def migrate(cr, version):
    if not (sql.column_exists(cr, TABLE, "created_by_name")
            and sql.column_exists(cr, TABLE, "created_by_employee_id")):
        return
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    cr.execute(f"""
        SELECT id, created_by_name FROM {TABLE}
         WHERE COALESCE(TRIM(created_by_name), '') != '' AND created_by_employee_id IS NULL
    """)
    rows = cr.fetchall()
    employees = {}
    for employee in env["hr.employee"].search([]):
        employees.setdefault(" ".join(employee.name.lower().split()), []).append(employee.id)

    unmatched = {}
    for spk_id, name in rows:
        matches = employees.get(" ".join(name.lower().split()), [])
        if len(matches) == 1:
            # In SQL: no tracking message and no approval or lock rule on a plain data move.
            cr.execute(f"UPDATE {TABLE} SET created_by_employee_id = %s WHERE id = %s", (matches[0], spk_id))
        else:
            unmatched[spk_id] = name.strip()

    for spk in env["fleet.spk"].browse(list(unmatched)):
        spk.message_post(body=Markup("%s <b>%s</b>. %s") % (
            "Created By (Print Out) sekarang dipilih dari Employee. Nama lama:",
            unmatched[spk.id],
            "Tidak ditemukan tepat satu Employee dengan nama ini, silakan pilih ulang.",
        ))
    _logger.info("SPK Created By: %s names moved to employees, %s not found.",
                 len(rows) - len(unmatched), len(unmatched))

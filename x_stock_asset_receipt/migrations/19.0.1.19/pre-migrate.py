"""Drop the free-text operational location fields from the stored views.

``operational_city`` and ``operational_province`` leave this module; x_spk shows
``operational_city_id`` and ``operational_province_id`` instead. The stored x_spk form
still names the old fields, and any module loaded between this one and x_spk (such as
x_leasing_amortization) validates the fleet.vehicle form with that stale copy. Every
module showing them depends on this one, so the cleanup runs here, before all of them.
The x_spk 19.0.1.6.5 migration moves the data to the new fields.
"""

import json
import re

OLD_FIELD = re.compile(r'<field\s+name="operational_(?:city|province)"[^>]*?/>\s*')


def migrate(cr, version):
    cr.execute("""
        SELECT id, arch_db FROM ir_ui_view
         WHERE type != 'qweb'
           AND (arch_db::text LIKE %s OR arch_db::text LIKE %s)
    """, ('%operational_city%', '%operational_province%'))
    for view_id, arch in cr.fetchall():
        cleaned = {lang: OLD_FIELD.sub('', text) for lang, text in arch.items()}
        if cleaned != arch:
            cr.execute("UPDATE ir_ui_view SET arch_db = %s WHERE id = %s", (json.dumps(cleaned), view_id))

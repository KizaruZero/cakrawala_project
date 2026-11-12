"""Drop the removed ``insurance_coverage`` field from the stored views.

The stored copy of the document form still names it, and Odoo can validate that
copy while loading the module's other views, before the XML replaces it.
"""

import json
import re

OLD_FIELD = re.compile(r'<field\s+name="insurance_coverage"[^>]*?/>\s*')


def migrate(cr, version):
    cr.execute("SELECT id, arch_db FROM ir_ui_view WHERE arch_db::text LIKE %s", ('%insurance_coverage%',))
    for view_id, arch in cr.fetchall():
        cleaned = {lang: OLD_FIELD.sub('', text) for lang, text in arch.items()}
        if cleaned != arch:
            cr.execute("UPDATE ir_ui_view SET arch_db = %s WHERE id = %s", (json.dumps(cleaned), view_id))

"""Drop the removed ``created_by_name`` field from the stored SPK form views.

Odoo can validate the stored copy while loading the module's other views, before
the XML replaces it with ``created_by_employee_id``.
"""

import json
import re

OLD_FIELD = re.compile(r'<field\s+name="created_by_name"[^>]*?/>\s*')


def migrate(cr, version):
    cr.execute("SELECT id, arch_db FROM ir_ui_view WHERE type != 'qweb' AND arch_db::text LIKE %s",
               ('%created_by_name%',))
    for view_id, arch in cr.fetchall():
        cleaned = {lang: OLD_FIELD.sub('', text) for lang, text in arch.items()}
        if cleaned != arch:
            cr.execute("UPDATE ir_ui_view SET arch_db = %s WHERE id = %s", (json.dumps(cleaned), view_id))

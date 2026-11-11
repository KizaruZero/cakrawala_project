"""Drop the free-text operational location fields from the stored views.

``operational_city`` and ``operational_province`` leave ``x_stock_asset_receipt``.
The stored copy of our form view still names them, and Odoo validates it while
loading the module's earlier views, before the XML replaces it. The new fields are
put back when the XML loads.
"""

import json
import re

OLD_FIELD = re.compile(r'<field\s+name="operational_(?:city|province)"[^>]*?/>\s*')


def migrate(cr, version):
    cr.execute("""
        SELECT id, arch_db FROM ir_ui_view
         WHERE arch_db::text LIKE '%%operational_city%%' OR arch_db::text LIKE '%%operational_province%%'
    """, ())
    for view_id, arch in cr.fetchall():
        cleaned = {lang: OLD_FIELD.sub('', text) for lang, text in arch.items()}
        if cleaned != arch:
            cr.execute("UPDATE ir_ui_view SET arch_db = %s WHERE id = %s", (json.dumps(cleaned), view_id))

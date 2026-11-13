"""Point the stored form view at the new Tipe Asuransi field before the views reload.

The first view of inherite_templates.xml is validated together with the stored arch of
view_contract_form_inherit_rename_label, which still names the removed selection field
until that later record of the file is loaded.
"""

import json

OLD = 'name="insurance_type"'
NEW = 'name="insurance_type_id"'


def migrate(cr, version):
    cr.execute("""
        SELECT v.id, v.arch_db FROM ir_ui_view v
          JOIN ir_model_data d ON d.model = 'ir.ui.view' AND d.res_id = v.id
         WHERE d.module = 'x_fleet_document' AND d.name = 'view_contract_form_inherit_rename_label'
    """)
    for view_id, arch in cr.fetchall():
        if not arch:
            continue
        arch = {lang: text.replace(OLD, NEW) for lang, text in arch.items()}
        cr.execute("UPDATE ir_ui_view SET arch_db = %s::jsonb WHERE id = %s", (json.dumps(arch), view_id))

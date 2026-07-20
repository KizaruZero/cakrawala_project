def migrate(cr, version):
    """Patch the stored Sub Type view arch before the module views reload.

    This version renames fleet.vehicle.sub_type (Char) to sub_type_id (Many2one).
    The model loads with the field already renamed, but the fleet.vehicle form is
    reassembled from every inheriting view still stored in the database — and the
    old Sub Type view there still points at "sub_type". That stale reference makes
    the combined form fail validation before the new arch is written, so it has to
    be fixed up first.
    """
    cr.execute(
        """
        UPDATE ir_ui_view v
           SET arch_db = (
                   SELECT jsonb_object_agg(
                              t.key,
                              replace(t.value, 'name="sub_type"', 'name="sub_type_id"')
                          )
                     FROM jsonb_each_text(v.arch_db) AS t
               )
          FROM ir_model_data d
         WHERE d.model = 'ir.ui.view'
           AND d.module = 'x_fleet_document'
           AND d.name = 'view_fleet_vehicle_form_inherit_sub_type'
           AND d.res_id = v.id
        """
    )

def migrate(cr, version):
    """Strip the removed Product/Item field from the stored Free Service view archs.

    fleet_spk_views.xml loads before free_service_information_views.xml, so the
    combined fleet.spk form is re-validated while these child views still hold
    their old arch from the database — which references product_id, a field this
    version removes. Validation would fail before the new arch is ever written,
    so the old arch has to be cleaned up first.
    """
    cr.execute(
        """
        UPDATE ir_ui_view v
           SET arch_db = (
                   SELECT jsonb_object_agg(
                              t.key,
                              replace(t.value, '<field name="product_id"/>', '')
                          )
                     FROM jsonb_each_text(v.arch_db) AS t
               )
          FROM ir_model_data d
         WHERE d.model = 'ir.ui.view'
           AND d.module = 'x_spk'
           AND d.res_id = v.id
           AND d.name IN (
                   'fleet_vehicle_form_free_service_inherit',
                   'fleet_spk_form_free_service_inherit'
               )
           AND v.arch_db::text LIKE '%product_id%'
        """
    )

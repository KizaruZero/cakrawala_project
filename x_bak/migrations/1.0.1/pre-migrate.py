def migrate(cr, version):
    cr.execute(
        "ALTER TABLE fleet_spk DROP CONSTRAINT IF EXISTS fleet_spk_bak_id_fkey"
    )
    cr.execute("""
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'fleet_spk'
           AND column_name = 'bak_id'
    """)
    if cr.fetchone():
        cr.execute("ALTER TABLE fleet_spk DROP COLUMN bak_id")

    cr.execute("""
        DELETE FROM ir_model_fields
         WHERE model = 'fleet.spk'
           AND name = 'bak_id'
    """)

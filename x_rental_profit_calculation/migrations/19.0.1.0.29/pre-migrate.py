WILAYAH_TYPES = {
    'wilayah_type_batas_atas': {
        'name': 'Batas Atas',
        'code': 'batas_atas',
    },
    'wilayah_type_batas_bawah': {
        'name': 'Batas Bawah',
        'code': 'batas_bawah',
    },
    'wilayah_type_crs': {
        'name': 'CRS',
        'code': 'crs',
    },
}


def migrate(cr, version):
    """Bind seeded XML IDs to legacy master records before data loading."""
    for xmlid_name, values in WILAYAH_TYPES.items():
        cr.execute(
            """
            SELECT id
              FROM rpc_wilayah_type
             WHERE LOWER(name) = LOWER(%s)
             ORDER BY id
             LIMIT 1
            """,
            (values['name'],),
        )
        row = cr.fetchone()
        if not row:
            cr.execute(
                """
                SELECT id
                  FROM rpc_wilayah_type
                 WHERE code = %s
                 ORDER BY id
                 LIMIT 1
                """,
                (values['code'],),
            )
            row = cr.fetchone()
        if not row:
            # A fresh installation has no legacy record. The XML data file
            # will create it normally after this pre-migration.
            continue

        cr.execute(
            """
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES (%s, %s, %s, %s, TRUE)
            ON CONFLICT (module, name)
            DO UPDATE SET
                model = EXCLUDED.model,
                res_id = EXCLUDED.res_id,
                noupdate = TRUE
            """,
            (
                'x_rental_profit_calculation',
                xmlid_name,
                'rpc.wilayah.type',
                row[0],
            ),
        )

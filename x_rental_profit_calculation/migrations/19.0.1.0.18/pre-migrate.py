PARAMETERS = {
    'parameter_jenis_kendaraan_non_bus_non_truk': {
        'code': 'non_bus_non_truk',
        'names': ('Non-Bus & Non-Truk', 'Non Bus & Non Truk'),
    },
    'parameter_jenis_kendaraan_truk_pickup': {
        'code': 'truk_pickup',
        'names': ('Truk & Pick-Up', 'Truk & Pickup'),
    },
    'parameter_jenis_kendaraan_bus': {
        'code': 'bus',
        'names': ('Bus',),
    },
    'parameter_jenis_kendaraan_roda_2': {
        'code': 'roda_2',
        'names': ('Roda 2', 'Roda Dua'),
    },
}


def migrate(cr, version):
    for xmlid_name, values in PARAMETERS.items():
        cr.execute(
            """
            SELECT 1
              FROM ir_model_data
             WHERE module = %s
               AND name = %s
             LIMIT 1
            """,
            ('x_rental_profit_calculation', xmlid_name),
        )
        if cr.fetchone():
            continue

        cr.execute(
            """
            SELECT id
              FROM rpc_parameter
             WHERE parameter_type = %s
               AND code = %s
             ORDER BY id
             LIMIT 1
            """,
            ('jenis_kendaraan', values['code']),
        )
        row = cr.fetchone()
        if not row:
            for name in values['names']:
                cr.execute(
                    """
                    SELECT id
                      FROM rpc_parameter
                     WHERE parameter_type = %s
                       AND LOWER(name) = LOWER(%s)
                     ORDER BY id
                     LIMIT 1
                    """,
                    ('jenis_kendaraan', name),
                )
                row = cr.fetchone()
                if row:
                    break

        if row:
            cr.execute(
                """
                INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (module, name) DO NOTHING
                """,
                (
                    'x_rental_profit_calculation',
                    xmlid_name,
                    'rpc.parameter',
                    row[0],
                ),
            )

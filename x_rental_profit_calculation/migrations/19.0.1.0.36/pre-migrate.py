MODULE = 'x_rental_profit_calculation'
XMLID = 'finance_line_type_rental_income_month'


def migrate(cr, version):
    """Bind T8 to an existing manual master record before XML data loads."""
    cr.execute(
        """
        SELECT id
          FROM rpc_finance_line_type
         WHERE code = %s
            OR (
                table_type = 'cashflow'
                AND LOWER(name) = LOWER(%s)
            )
         ORDER BY id
         LIMIT 1
        """,
        ('rental_income_month', 'T8 PENDAPATAN SEWA/BULAN'),
    )
    row = cr.fetchone()
    if not row:
        return

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
        (MODULE, XMLID, 'rpc.finance.line.type', row[0]),
    )

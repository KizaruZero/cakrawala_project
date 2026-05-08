"""Migrate bastk.management.asset_number from Many2one integer+FKEY to varchar."""

from odoo.tools.sql import SQL


def migrate(cr, version):
    cr.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'bastk_management'
        )
        """
    )
    if not cr.fetchone()[0]:
        return

    cr.execute(
        """
        SELECT c.conname
        FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        JOIN pg_namespace n ON t.relnamespace = n.oid
        WHERE n.nspname = 'public'
          AND t.relname = 'bastk_management'
          AND c.contype = 'f'
          AND EXISTS (
              SELECT 1
              FROM unnest(c.conkey) AS ck(attnum)
              JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ck.attnum
              WHERE a.attname = 'asset_number'
          )
        """
    )
    for (conname,) in cr.fetchall():
        cr.execute(
            SQL(
                "ALTER TABLE %s DROP CONSTRAINT %s",
                SQL.identifier("bastk_management"),
                SQL.identifier(conname),
            )
        )

    cr.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'bastk_management'
          AND column_name = 'asset_number'
        """
    )
    row = cr.fetchone()
    if not row:
        return
    dtype = row[0]
    if dtype in ("integer", "bigint", "smallint"):
        cr.execute(
            """
            ALTER TABLE bastk_management
            ALTER COLUMN asset_number TYPE VARCHAR
            USING CASE WHEN asset_number IS NOT NULL THEN asset_number::text ELSE NULL END
            """
        )

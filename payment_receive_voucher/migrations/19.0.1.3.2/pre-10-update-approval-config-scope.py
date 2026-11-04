def migrate(cr, version):
    cr.execute("""
        SELECT conname
          FROM pg_constraint
         WHERE conrelid = 'prv_voucher_config'::regclass
           AND contype = 'u'
           AND pg_get_constraintdef(oid) = 'UNIQUE (company_id, voucher_type)'
    """)
    for (constraint_name,) in cr.fetchall():
        quoted_name = constraint_name.replace('"', '""')
        cr.execute(f'ALTER TABLE prv_voucher_config DROP CONSTRAINT "{quoted_name}"')

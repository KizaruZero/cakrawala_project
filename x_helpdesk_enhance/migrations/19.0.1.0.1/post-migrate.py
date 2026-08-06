def migrate(cr, version):
    if not version:
        return

    # Update employee_id based on the existing user_id
    cr.execute("""
        UPDATE helpdesk_ticket ht
        SET employee_id = he.id
        FROM hr_employee he
        WHERE ht.user_id = he.user_id
        AND ht.employee_id IS NULL
    """)

def migrate(cr, version):
    # Metadata only: identify historical generated bills from their real loan
    # relation. Never infer a financial workflow from free-text Bill Reference.
    cr.execute("""
        UPDATE account_move
           SET is_early_settlement = TRUE
         WHERE early_settlement_loan_id IS NOT NULL
           AND move_type = 'in_invoice'
           AND is_early_settlement IS NOT TRUE
    """)

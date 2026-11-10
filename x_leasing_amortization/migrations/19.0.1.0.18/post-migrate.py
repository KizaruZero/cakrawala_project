def migrate(cr, version):
    """Backfill PO Number on loans linked to a Purchase Order but left blank."""
    cr.execute("""
        UPDATE account_loan loan
           SET po_number = po.name
          FROM purchase_order po
         WHERE loan.purchase_order_id = po.id
           AND COALESCE(loan.po_number, '') = ''
    """)

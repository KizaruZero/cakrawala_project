def migrate(cr, version):
    """The group record is noupdate, so the XML alone cannot detach it from
    the Employee Purchase Requisition privilege, where it was rendered as an
    exclusive dropdown option instead of an Extra Rights checkbox."""
    cr.execute("""
        UPDATE res_groups
           SET privilege_id = NULL
         WHERE id = (
                SELECT res_id
                  FROM ir_model_data
                 WHERE module = 'x_purchase_request_create_po'
                   AND name = 'group_create_po_from_pr_line'
                   AND model = 'res.groups'
               )
    """)

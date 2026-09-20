def migrate(cr, version):
    """Move legacy RPC links to the shared quotation relation."""
    cr.execute(
        """
        INSERT INTO rpc_document_sale_order_rel (rpc_document_id, sale_order_id)
        SELECT rpc_document_id, id
          FROM sale_order
         WHERE rpc_document_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    # Existing approved RPCs predate the director price-selection popup.
    # Preserve their former quotation behaviour by taking the upper price.
    cr.execute(
        """
        UPDATE rpc_document
           SET final_rental_price_type = 'upper',
               final_rental_price = sewa_per_bulan_batas_atas
         WHERE state = 'approved'
           AND final_rental_price_type IS NULL
        """
    )

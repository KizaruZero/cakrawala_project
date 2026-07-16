def migrate(cr, version):
    """Drop the Product/Item column left behind by removing free.service.item.product_id.

    Odoo never drops columns for removed fields, and this one carries a foreign
    key to product_product that would keep blocking product deletion.
    """
    cr.execute(
        """
        ALTER TABLE free_service_item
         DROP COLUMN IF EXISTS product_id
        """
    )

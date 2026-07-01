def migrate(cr, version):
    cr.execute(
        """
        UPDATE product_template
           SET is_storable = FALSE,
               tracking = 'none'
         WHERE spk_category = 'external'
           AND (is_storable = TRUE OR tracking != 'none')
        """
    )

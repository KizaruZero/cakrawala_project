"""19.0.0.63: Syarat dan Ketentuan dihapus dari Rental Order.

View sale_order_form_notes yang tersimpan masih menyebut field x_terms_conditions. Kalau
dibiarkan, view sale.order lain di modul ini gagal divalidasi sebelum view itu sempat
diperbarui. View lama dihapus di sini, lalu dibuat lagi dari XML saat modul dimuat.
"""


def migrate(cr, version):
    cr.execute("""
        DELETE FROM ir_ui_view
         WHERE id IN (SELECT res_id FROM ir_model_data
                       WHERE module = 'x_sale_purchase_custom'
                         AND name = 'sale_order_form_notes'
                         AND model = 'ir.ui.view')
    """)
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module = 'x_sale_purchase_custom'
           AND name = 'sale_order_form_notes'
           AND model = 'ir.ui.view'
    """)

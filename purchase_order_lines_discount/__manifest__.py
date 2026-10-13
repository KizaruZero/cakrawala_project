# -*- coding: utf-8 -*-
{
    'name': "Purchase Discount|Purchase Fixed Discount|Purchase Percentage Discount",

    'summary': "Fixed and percentage discounts on purchase order lines (Odoo 19)",

    'description': """
        Adds a fixed discount amount to purchase order lines and carries its exact
        value into vendor bills and receipt valuation. Percentage discounts and
        lines without a fixed discount continue to use Odoo's standard behavior.
    """,

    'images': ["static/description/main_banner.png"],
    'author': "Sayed Hassan",
    'version': '19.0.1.2.2',
    'license': "AGPL-3",
    'category': "Purchase Management",

    # any module necessary for this one to work correctly
    'depends': ['base', 'purchase', 'purchase_stock'],

    # always loaded
    'data': [
        'views/purchase_order_view.xml',
    ]
}

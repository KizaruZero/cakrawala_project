# -*- coding: utf-8 -*-
{
    'name': "Sales Purchase Custom",
    'summary': "Integration between Sales Order, Purchase Request, and Purchase Order based on Rental Type.",
    'description': """
        This module adds a Rental Type master data and integrates SO to PR/PO generation.
    """,
    'author': "Odoo Developer",
    'category': 'Custom',
    'version': '0.1',
    'depends': ['sale_management', 'sale_renting', 'purchase', 'employee_purchase_requisition', 'x_rental_profit_calculation'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_rental_type_views.xml',
        'views/sale_order_views.xml',
        'views/employee_purchase_requisition_views.xml',
        'views/purchase_order_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'x_sale_purchase_custom/static/src/js/daterange_patch.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

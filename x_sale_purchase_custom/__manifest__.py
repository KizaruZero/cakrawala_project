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
    'depends': ['sale_management', 'purchase', 'employee_purchase_requisition'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_rental_type_views.xml',
        'views/sale_order_views.xml',
        'views/employee_purchase_requisition_views.xml',
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

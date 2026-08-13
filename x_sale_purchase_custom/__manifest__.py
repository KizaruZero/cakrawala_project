# -*- coding: utf-8 -*-
{
    'name': "Sales Purchase Custom",
    'license': 'LGPL-3',
    'summary': "Integration between Sales Order, Purchase Request, and Purchase Order based on Rental Type. Includes Monthly Rental Invoicing.",
    'description': """
        This module adds a Rental Type master data, integrates SO to PR/PO generation,
        and provides automated Monthly Rental Invoicing with prorate support.
    """,
    'author': "Odoo Developer",
    'category': 'Custom',
    'version': '0.3',
    'depends': [
        'sale_management',
        'sale_renting',
        'purchase',
        'account',
        'stock',
        'fleet',
        'employee_purchase_requisition',
        'x_rental_profit_calculation',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/rental_invoice_config.xml',
        'data/rental_invoice_cron.xml',
        'views/sale_rental_type_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/employee_purchase_requisition_views.xml',
        'views/purchase_order_views.xml',
        'wizard/rental_invoice_trigger_wizard_views.xml',
        'reports/report_pks_payung.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'x_sale_purchase_custom/static/src/js/daterange_patch.js',
            'x_sale_purchase_custom/static/src/js/archive_blocking.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

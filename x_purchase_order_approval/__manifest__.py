# -*- coding: utf-8 -*-
{
    'name': "x_purchase_order_approval",
    'summary': "Purchase order approval",
    'description': "Custom addons for purchase order approval",
    'author': "Doni Hadiansyah - Xapiens Teknologi Indonesia",
    'website': "https://xapiens.id",
    'category': 'Purchase Approval',
    'license': 'AGPL-3',
    'version': '0.2',
    'depends': ['base','web','hr','purchase','account','account_budget','purchase_requisition','x_analytic_distribution_validation'],
    'data': [
        'security/ir.model.access.csv',
        'security/purchase_order_approval_security.xml',
        'wizard/po_reject_reason_wizard_views.xml',
        'views/res_company_views.xml',
        'views/res_partner_views.xml',
        'views/product_views.xml',
        'views/master_data_views.xml',
        'views/purchase_views.xml',
        'views/report_actions.xml',
        'report/po_custom_templates.xml',
        'data/mail_template_data.xml',
        'data/res_groups.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
    'assets': {
        'web.assets_backend': [
            'x_purchase_order_approval/static/src/js/archive_blocking.js',
        ],
    },
}
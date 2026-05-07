# -*- coding: utf-8 -*-
{
    'name': "x_purchase_request_create_po",
    'summary': "Purchase request create PO",
    'description': "Custom addons for purchase request create Purchase Order",
    'author': "Ibnu Nur Khawarizmi - Xapiens Teknologi Indonesia",
    'website': "https://xapiens.id",
    'category': 'Purchase Request',
    'license': 'AGPL-3',
    'version': '0.1',
    'depends': ['x_purchase_request_approval'],
    'data': [
        'views/employee_purchase_requisition_view.xml',
        'views/purchase_order_view.xml',
        'wizard/pr_create_po_wizard_view.xml',
        'data/menu_item.xml',
        'data/ir_rule.xml',
        'security/ir.model.access.csv',
        'data/res_groups.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
}
{
    'name': 'PO Report Custom',
    'version': '1.0',
    'summary': 'Custom Reporting for Purchase Order',
    'author': 'Your Company',
    'category': 'Purchase',
    'depends': [
        'purchase',
        'stock',
        'fleet',
        'purchase_down_payment',
        'x_sale_purchase_custom',
        'x_stock_asset_receipt'
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/po_report_views.xml',
        'report/report_actions.xml',
        'report/po_report_templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

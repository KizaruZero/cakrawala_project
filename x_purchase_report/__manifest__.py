{
    'name': 'x_purchase_report',
    'version': '19.0.1.0.0',
    'category': 'Purchase',
    'summary': 'Custom purchase order reports',
    'author': 'Cakrawala',
    'license': 'LGPL-3',
    'depends': ['purchase','x_purchase_request_approval', 'x_purchase_order_approval'],
    'data': [
        'report/purchase_report_templates.xml',
        'report/purchase_wrapper_templates.xml',
        'report/purchase_override_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'assets': {
        'web.report_assets_common': [
            'x_purchase_report/static/scss/report.scss',
        ],
    },
}
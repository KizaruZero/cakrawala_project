{
    'name': 'BASTK Report',
    'version': '1.0',
    'category': 'Fleet Custom',
    'summary': 'Custom PDF Printouts for BASTK Out and BASTK In',
    'depends': ['base', 'fleet', 'x_bastk_management'],
    'data': [
        'report/bastk_report_actions.xml',
        'report/bastk_out_report_templates.xml',
        'report/bastk_in_report_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}

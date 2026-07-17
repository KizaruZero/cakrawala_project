# -*- coding: utf-8 -*-
{
    'name': 'OMON -',
    'version': '19.0.1.0.0',
    'category': 'Technical Settings',
    'summary': 'Mengirim status instance (user, expired, domain, dll) ke dashboard monitoring eksternal',
    'description': """

""",
    'author': 'Xapiens',
    'website': 'https://xapiens.id',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'data/default_config_data.xml',
        'views/subscription_monitor_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': True,
}

{
    'name': 'Service Planning',
    'version': '1.0',
    'summary': 'Service Planning for Vehicle',
    'depends': ['base', 'fleet', 'product', 'x_fleet_document', 'mail', 'x_email_notification'],
    'category': 'Fleet Custom',
    'license': 'LGPL-3',

    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/service_planning_cron.xml',
        'data/mail_template_data.xml',
        'views/service_planning_views.xml',
        'views/fleet_vehicle_views.xml',
    ],
    'installable': True,
    'application': True,
}
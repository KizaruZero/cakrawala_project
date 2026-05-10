{
    'name': 'Replacement Car',
    'version': '1.0',
    'summary': 'Fleet Replacement Car Management',
    'category': 'Fleet Custom',
    'depends': ['fleet', 'x_service_planning', 'x_spk', 'x_fleet_document'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/replacement_car_views.xml',
        'views/fleet_spk_views.xml',
    ],
    'installable': True,
    'application': True,
}
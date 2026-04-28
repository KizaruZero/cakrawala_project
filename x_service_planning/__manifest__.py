{
    'name': 'Service Planning',
    'version': '1.0',
    'summary': 'Service Planning for Vehicle',
    'depends': ['base', 'fleet', 'product'],
    'category': 'Fleet Custom',
    'license': 'LGPL-3',

    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/service_planning_views.xml',
        'views/fleet_vehicle_views.xml',
    ],
    'installable': True,
    'application': True,
}
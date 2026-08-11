{
    'name': 'BAK (Berita Acara Kejadian)',
    'version': '1.0.3',
    'summary': 'BAK Module',
    'category': 'Fleet Custom',
    'author': 'Kurnia Galuh',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'fleet',
        'mail',
        'account',
        'x_spk',
    ],
    "assets": {
        "web.assets_backend": [
            "x_bak/static/src/js/bak_form.js",
        ],
    },
    'data': [
        'security/bak_security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/bak_category_data.xml',
        "report/bak_report.xml",
        'views/bak_category_views.xml',
        'views/bak_views.xml',
        'views/fleet_spk_views_inherit.xml',
        'views/fleet_vehicle_views.xml',
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': True,
}
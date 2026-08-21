# -*- coding: utf-8 -*-
{
    'name': "x_analytic_distribution_validation",
    'summary': "Analytic distribution must total exactly 100%",
    'description': """
Analytic Distribution 100% Validation
=====================================

Odoo bawaan hanya memvalidasi analytic distribution untuk plan yang
applicability-nya 'mandatory'. Akibatnya user bisa menyimpan distribusi
50%, atau bahkan 180% (misal line 1 = 100%, line 2 = 80%) tanpa ditolak.

Modul ini menambahkan constraint keras pada 'analytic.mixin' sehingga
seluruh model yang memakai analytic distribution (invoice, bill, journal
entry, PO, PR, SO, asset, expense) wajib bertotal tepat 100% apabila
analytic distribution diisi. Mengosongkan analytic distribution tetap
diperbolehkan.
    """,
    'author': "Xapiens Teknologi Indonesia",
    'website': "https://xapiens.id",
    'category': 'Accounting/Accounting',
    'license': 'AGPL-3',
    'version': '0.1',
    'depends': ['analytic'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'x_analytic_distribution_validation/static/src/js/analytic_distribution_total_warning.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'application': False,
    'installable': True,
    'auto_install': False,
}

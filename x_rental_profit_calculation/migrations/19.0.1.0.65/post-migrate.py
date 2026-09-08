# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Link T4 to incentive totals and refresh generated Finance lines."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    incentive_type = env['rpc.finance.line.type'].search([
        ('code', '=', 'post_insentif'),
    ], limit=1)
    if incentive_type:
        incentive_type.write({
            'formula_batas_atas': 'incentive_upper',
            'formula_batas_bawah': 'incentive_lower',
        })

    documents = env['rpc.document'].search([
        ('state', 'in', ('finance_done', 'approved')),
    ])
    documents._generate_finance_lines()

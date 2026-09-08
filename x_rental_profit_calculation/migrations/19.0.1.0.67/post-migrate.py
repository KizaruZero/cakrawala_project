# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Refresh Finance lines after correcting the T7 Gapping formula."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    documents = env['rpc.document'].search([
        ('state', 'in', ('finance_done', 'approved')),
    ])
    documents._generate_finance_lines()

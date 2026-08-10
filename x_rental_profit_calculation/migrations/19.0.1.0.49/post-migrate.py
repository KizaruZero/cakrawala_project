# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Generate HOK tables for existing documents whose calculation is ready."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    documents = env['rpc.document'].search([
        ('state', 'in', ('finance_done', 'approved')),
        ('hok', '=', 'yes'),
    ])
    documents._generate_hok_lines()

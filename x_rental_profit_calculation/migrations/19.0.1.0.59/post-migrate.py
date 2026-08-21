# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Refresh HOK matrices with the prorated total Funding OPEX."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    documents = env['rpc.document'].search([
        ('state', 'in', ('finance_done', 'approved')),
    ])
    documents._generate_logic_table_lines()

# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Backfill OPEX and integrated Funding/Gapping hierarchy rows."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    documents = env['rpc.document'].search([
        ('state', 'in', ('finance_done', 'approved')),
    ])
    documents._compute_replacement_ratio()
    documents._generate_logic_table_lines()

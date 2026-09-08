# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Convert STNK and Service year ordinals to calendar years."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    documents = env['rpc.document'].search([
        ('tahun_mulai_sewa', '>', 0),
    ])
    documents._sync_operational_line_years()

    calculated_documents = documents.filtered(
        lambda document: document.state in ('finance_done', 'approved')
    )
    calculated_documents._generate_logic_table_lines()
    calculated_documents._generate_finance_lines()

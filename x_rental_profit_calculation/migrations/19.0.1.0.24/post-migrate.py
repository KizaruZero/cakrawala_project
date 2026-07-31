from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    documents = env['rpc.document'].search([
        ('state', 'in', ('finance_done', 'approved')),
    ])
    documents._generate_finance_lines()

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Recompute insurance amounts from OTR Final and rebuild Logic Table."""
    env = api.Environment(cr, SUPERUSER_ID, {})

    insurance_lines = env['rpc.document.insurance.line'].search([])
    insurance_lines._compute_amount()
    env.flush_all()

    documents = env['rpc.document'].with_context(active_test=False).search([
        ('state', 'in', ('finance_done', 'approved')),
    ])
    documents._generate_logic_table_lines()

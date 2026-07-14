from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # Percentage widgets store 4.2% as 0.042, not 4.2.
    cr.execute("""
        UPDATE rpc_asuransi_rate
           SET rate = rate / 100.0
         WHERE rate > 1.0
    """)

    env = api.Environment(cr, SUPERUSER_ID, {})
    documents = env['rpc.document'].search([
        ('state', '=', 'finance_done'),
        ('insurance_type', '!=', False),
        ('tahun_mulai_sewa', '>', 0),
        ('masa_sewa', '>', 0),
    ])
    documents._generate_insurance_lines(raise_if_incomplete=False)

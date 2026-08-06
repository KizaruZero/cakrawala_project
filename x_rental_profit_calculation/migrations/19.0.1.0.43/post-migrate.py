from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Rebuild Logic Table and its Funding/Gapping yearly summaries."""
    env = api.Environment(cr, SUPERUSER_ID, {})

    mk04_logic = env['rpc.hierarchy.logic'].with_context(
        active_test=False
    ).search([
        ('cost_group_code_id.name', '=', 'MK04'),
    ])
    mk04_logic.write({
        'formula': (
            'lainnya_marketing * ((1 + horizon_bulan_tahun) / 2) '
            '* jumlah_unit'
        ),
    })

    documents = env['rpc.document'].with_context(active_test=False).search([
        ('state', 'in', ('finance_done', 'approved')),
    ])
    documents._generate_logic_table_lines()

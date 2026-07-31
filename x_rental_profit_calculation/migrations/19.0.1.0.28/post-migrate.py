from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    documents = env['rpc.document'].search([
        ('state', 'in', ('finance_done', 'approved')),
    ])

    insurance_documents = documents.filtered(
        lambda document: (
            document.insurance_type
            and document.tahun_mulai_sewa > 0
            and document.masa_sewa > 0
        )
    )
    insurance_documents._generate_insurance_lines(raise_if_incomplete=False)
    documents._generate_finance_lines()
    documents._generate_logic_table_lines()

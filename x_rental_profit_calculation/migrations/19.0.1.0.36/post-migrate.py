from odoo import SUPERUSER_ID, api


FINANCE_TYPE_VALUES = {
    'cof_month_year_1': {
        'formula_batas_atas': 'cof_month_year_1',
        'formula_batas_bawah': 'cof_month_year_1',
    },
    'cof_month_year_2_onwards': {
        'formula_batas_atas': 'cof_month_year_2_onwards',
        'formula_batas_bawah': 'cof_month_year_2_onwards',
    },
    'ncf_month_year_1': {
        'formula_batas_atas': 'ncf_month_year_1_upper',
        'formula_batas_bawah': 'ncf_month_year_1_lower',
    },
    'ncf_month_year_2_onwards': {
        'formula_batas_atas': 'ncf_month_year_2_upper',
        'formula_batas_bawah': 'ncf_month_year_2_lower',
    },
    'gapping_month_year_1': {
        'name': 'T6 GAPPING/BULAN THN 1',
        'formula_batas_atas': 'gapping_month_year_1_upper',
        'formula_batas_bawah': 'gapping_month_year_1_lower',
    },
    'gapping_month_year_2_onwards': {
        'name': 'T7 GAPPING/BULAN THN 2-DST',
        'formula_batas_atas': 'gapping_month_year_2_upper',
        'formula_batas_bawah': 'gapping_month_year_2_lower',
    },
    'rental_income_month': {
        'name': 'T8 PENDAPATAN SEWA/BULAN',
        'formula_batas_atas': 'rental_income_total_upper',
        'formula_batas_bawah': 'rental_income_total_lower',
    },
}


def migrate(cr, version):
    """Apply CSV formulas to master data and refresh generated Finance rows."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    type_model = env['rpc.finance.line.type'].with_context(active_test=False)

    for code, values in FINANCE_TYPE_VALUES.items():
        finance_type = type_model.search([('code', '=', code)], limit=1)
        if finance_type:
            finance_type.write(values)

    documents = env['rpc.document'].with_context(active_test=False).search([])
    documents._compute_consolidation()

    finance_documents = documents.filtered(
        lambda document: document.state in ('finance_done', 'approved')
    )
    finance_documents._generate_finance_lines()

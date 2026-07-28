from odoo import SUPERUSER_ID, api


LOGIC_FORMULAS = {
    'F01': 'total_downpayment',
    'F02': (
        '-(sewa_per_bulan - angsuran_per_bulan) '
        '* ((1 + max(masa_sewa, 12)) / 2)'
    ),
    'F03': '((TOP + offset pembayaran) / 30) * sewa_per_bulan',
    'BVK01': 'estimasi biaya STNK tahun berjalan * jumlah_unit',
    'BVK02': 'asuransi tahun berjalan * jumlah_unit',
    'BVK03': 'estimasi biaya service tahun berjalan * jumlah_unit',
    'BVK04': (
        '(akumulasi STNK + Asuransi + Service '
        '+ (otr_final * jumlah_unit * 12 / masa_sewa)) '
        '* replacement_car_ratio'
    ),
    'FT01': 'management_fee * jumlah_unit',
    'FT02': 'free_own_risk * jumlah_unit',
    'FT03': 'bank_garansi_deposit',
    'FT04': 'asuransi_jiwa_pa * jumlah_unit',
    'MK01': (
        'pic_internal * ((1 + (index_tahun * 12)) / 2) * jumlah_unit'
    ),
    'MK02': 'infrastruktur * jumlah_unit',
    'MK03': 'komisi_proyek * jumlah_unit',
    'MK04': 'lainnya_marketing * jumlah_unit',
}


def migrate(cr, version):
    """Synchronize updated functional formulas and rebuild Logic Table rows."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    logic_model = env['rpc.hierarchy.logic'].with_context(active_test=False)

    for code, formula in LOGIC_FORMULAS.items():
        logic = logic_model.search([
            ('cost_group_code_id.name', '=', code),
        ], limit=1)
        if logic:
            logic.formula = formula

    documents = env['rpc.document'].with_context(active_test=False).search([
        ('state', 'in', ('finance_done', 'approved')),
    ])
    documents._generate_logic_table_lines()

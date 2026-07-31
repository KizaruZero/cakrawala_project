from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    rate_model = env['rpc.asuransi.rate'].with_context(active_test=False)
    type_model = env['rpc.wilayah.type'].with_context(active_test=False)

    for code in ('batas_atas', 'batas_bawah', 'crs'):
        wilayah_type = type_model.search([('code', '=', code)], limit=1)
        if wilayah_type:
            rate_model.search([
                ('wilayah_type_id', '=', False),
                ('wilayah_type', '=', code),
            ]).write({'wilayah_type_id': wilayah_type.id})

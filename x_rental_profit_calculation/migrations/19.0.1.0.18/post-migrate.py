from odoo import SUPERUSER_ID, api


PARAMETER_XMLIDS = {
    'non_bus_non_truk': 'parameter_jenis_kendaraan_non_bus_non_truk',
    'truk_pickup': 'parameter_jenis_kendaraan_truk_pickup',
    'bus': 'parameter_jenis_kendaraan_bus',
    'roda_2': 'parameter_jenis_kendaraan_roda_2',
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    category_model = env['rpc.kendaraan.kategori'].with_context(active_test=False)

    for legacy_code, xmlid_name in PARAMETER_XMLIDS.items():
        parameter = env.ref(
            f'x_rental_profit_calculation.{xmlid_name}',
            raise_if_not_found=False,
        )
        if parameter:
            category_model.search([
                ('jenis_kendaraan_id', '=', False),
                ('jenis_kendaraan', '=', legacy_code),
            ]).write({'jenis_kendaraan_id': parameter.id})

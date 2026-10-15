import logging

from odoo import SUPERUSER_ID, api


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Refresh final-tenor PIC Internal and its dependent profitability rows.

    Keep the existing row IDs, approval state, inputs and Funding/Gapping
    schedules intact. This also updates previously approved RPC printouts and
    existing HOK results that depend on the RPC profit base, not HOK Cost Base.
    """
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    components = {'marketing', 'total_cost', 'profit_per_unit', 'profit_total_project'}
    documents = env['rpc.document'].search([
        ('rpc_profitability_line_ids', '!=', False),
        ('masa_sewa', '>', 0),
        ('otr_final', '>', 0),
    ])
    for document in documents:
        values_by_component = {
            values['component']: values
            for values in document._rpc_profitability_values()
            if values['component'] in components
        }
        for line in document.rpc_profitability_line_ids:
            if line.component in values_by_component:
                values = values_by_component[line.component]
                line.write({
                    field: values[field]
                    for field in (
                        'batas_atas', 'batas_bawah', 'percentage_batas_atas',
                        'percentage_batas_bawah', 'formula',
                    )
                })
        _refresh_hok_profit_results(document, values_by_component['profit_per_unit'])
    _logger.info('Updated final-tenor PIC profitability for %s RPCs.', len(documents))


def _refresh_hok_profit_results(document, profit_values):
    """Refresh only HOK results that consume Profit RPC; never rebuild tables."""
    if document.hok != 'yes' or document.tahun_mulai_sewa <= 0:
        return
    lines = document.hok_matrix_line_ids.filtered(lambda line: (
        line.section in ('upper', 'lower')
        and line.component_code in (
            'profit_base', 'profit_amount', 'rental_per_month', 'hok_holder_portion',
        )
    ))
    costs = {tenor: document._hok_cost_values(tenor) for tenor in set(lines.mapped('tenor_months'))}
    profit_bases = {
        limit: profit_values[limit] / document.otr_final
        for limit in ('batas_atas', 'batas_bawah')
    }
    for line in lines:
        limit = 'batas_atas' if line.section == 'upper' else 'batas_bawah'
        line.write({
            f'value_{rate}': document._hok_scenario_values(
                line.tenor_months, rate / 100.0, limit,
                costs=costs[line.tenor_months], profit_bases=profit_bases,
            )[line.component_code]
            for rate in range(0, 81, 10)
        })

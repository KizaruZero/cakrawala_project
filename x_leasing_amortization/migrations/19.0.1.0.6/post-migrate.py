from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Refresh only derived Payment Date, never names/due dates/journals."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    model = env['account.loan.line'].with_context(active_test=False)
    last_id = 0
    while lines := model.search([('id', '>', last_id)], order='id', limit=1000):
        last_id = lines[-1].id
        env.add_to_compute(lines._fields['payment_date'], lines)
        lines._recompute_recordset(['payment_date'])
        lines.flush_recordset(['payment_date'])

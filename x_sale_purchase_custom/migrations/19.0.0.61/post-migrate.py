from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Early Termination left Return Status for its own field: recount the orders holding the old value."""
    cr.execute("SELECT id FROM sale_order WHERE return_status = 'early_termination'")
    order_ids = [row[0] for row in cr.fetchall()]
    if order_ids:
        env = api.Environment(cr, SUPERUSER_ID, {})
        orders = env['sale.order'].browse(order_ids)
        env.add_to_compute(orders._fields['return_status'], orders)
        orders._recompute_recordset(['return_status'])
        orders.flush_recordset(['return_status'])

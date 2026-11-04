from odoo import Command, SUPERUSER_ID, api, fields


def migrate(cr, version):
    """Migrate legacy header-level ET records to sale.order.et.line and backfill UI fields."""
    env = api.Environment(cr, SUPERUSER_ID, {})

    # 1. Backfill payment_type_ui on existing payments
    cr.execute("""
        UPDATE account_payment
           SET payment_type_ui = CASE
               WHEN COALESCE(is_internal_transfer_custom, FALSE) IS TRUE THEN 'internal_transfer'
               ELSE COALESCE(payment_type, 'inbound')
           END,
               internal_transfer_direction = COALESCE(internal_transfer_direction, payment_type, 'inbound')
         WHERE payment_type_ui IS NULL
            OR internal_transfer_direction IS NULL
    """)

    # 2. Migrate historical header-level Early Termination data into sale.order.et.line
    legacy_et_orders = env['sale.order'].search([
        '|', '|',
        ('is_early_termination_requested', '=', True),
        ('et_is_approved', '=', True),
        ('et_return_picking_ids', '!=', False),
    ])
    ETLine = env['sale.order.et.line'].with_context(_et_system_update=True)
    for order in legacy_et_orders:
        if order.et_line_ids:
            continue
        if order.et_invoice_id:
            state = 'invoiced'
        elif order.et_is_approved:
            state = 'approved'
        else:
            state = 'pending'
        ETLine.create({
            'order_id': order.id,
            'sequence': 10,
            'name': 'ET-01',
            'termination_date': order.et_termination_date or fields.Date.today(),
            'sale_line_ids': [Command.set(order.et_return_line_ids.ids)],
            'return_picking_ids': [Command.set(order.et_return_picking_ids.ids)],
            'penalty_amount': order.et_penalty_amount or 0.0,
            'reason': order.et_reason or False,
            'notes': order.et_notes or False,
            'state': state,
            'approved_by': order.et_approved_by.id or False,
            'approval_date': order.et_approval_date or False,
            'is_delegated': bool(order.et_is_delegated),
            'delegator_id': order.et_delegator_id.id or False,
            'invoice_id': order.et_invoice_id.id or False,
        })

    # 3. Recompute contract_notification_status on rental orders
    rental_orders = env['sale.order'].search([('is_rental_order', '=', True)])
    if rental_orders:
        rental_orders._compute_contract_notification_status()

